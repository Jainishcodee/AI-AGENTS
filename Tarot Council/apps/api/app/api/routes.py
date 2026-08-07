"""HTTP surface. Thin: validate, call the council, stream events."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..core.errors import CognitiveOSError, ProgramInvalid
from ..council import Council
from ..engine.planner import call_estimate
from ..learning import priors
from ..learning.scoring import CHANCE_BRIER
from ..programs import loader
from ..schemas.cards import MIN_N_TO_DISPLAY, CardStatus, DecisionCard, Prior, Resolution
from ..schemas.common import Verdict
from ..schemas.council import Deliberation, DeliberationRequest
from ..schemas.events import sse

router = APIRouter()


class VerdictOverride(BaseModel):
    verdict: Verdict
    justification: str = ""


class RerunRequest(BaseModel):
    module: str
    from_stage: str
    facts: list[str] = Field(default_factory=list)
    """New information the earlier run did not have."""
    reason: str = ""


class RefineRequest(BaseModel):
    answers: list[str] = Field(min_length=1)
    """Answers to the unknowns the council raised."""
    reason: str = ""


def _council(request: Request) -> Council:
    return request.app.state.council


@router.get("/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "modules": sorted(loader.programs()),
        "presets": sorted(loader.presets()),
    }


@router.get("/modules")
async def modules() -> list[dict[str, object]]:
    """Public module specs.

    Biases are included deliberately: the product's claim is that reasoning is
    inspectable, and hiding a module's known failure modes from the user would
    contradict that. They are withheld only from the module *itself* (ADR-003).
    """
    out = []
    for program in loader.programs().values():
        out.append(
            {
                "id": program.id,
                "skin": program.skin.model_dump(),
                "summary": program.summary.strip(),
                "mental_model": program.mental_model.strip(),
                "stages": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "produces": s.produces,
                        "group": s.group,
                        "terminal": s.terminal,
                        "must_not": list(s.must_not),
                    }
                    for s in program.stages
                ],
                "biases": [
                    {
                        "id": b.id,
                        "description": b.description,
                        "hidden_from_self": True,
                        "detectable_by": list(b.detectable_by),
                    }
                    for b in program.biases
                ],
                "critics": list(program.critics),
                "success_metrics": [m.model_dump() for m in program.success_metrics],
                "risk_tolerance": program.risk_tolerance,
                "time_horizon": program.time_horizon,
                "veto_enabled": program.veto_enabled,
                "calls_per_depth": {
                    depth: call_estimate(program, depth)
                    for depth in ("quick", "standard", "deep")
                },
            }
        )
    return out


@router.get("/presets")
async def presets() -> list[dict[str, object]]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description.strip(),
            "primary": list(p.primary),
            "advisory": list(p.advisory),
            "critic": list(p.critic),
        }
        for p in loader.presets().values()
    ]


@router.get("/critique-matrix")
async def critique_matrix() -> dict[str, list[str]]:
    """Derived from each module's own `critics` list, never configured separately."""
    return {critic: list(targets) for critic, targets in loader.critique_matrix().items()}


@router.post("/council/deliberate")
async def deliberate(request: Request, body: DeliberationRequest) -> StreamingResponse:
    council = _council(request)
    _check_preset(body.preset)

    async def stream() -> AsyncIterator[str]:
        async for event in council.deliberate(body):
            yield sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


@router.post("/council/deliberate/sync")
async def deliberate_sync(request: Request, body: DeliberationRequest) -> Deliberation:
    _check_preset(body.preset)
    try:
        return await _council(request).run(body)
    except CognitiveOSError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/deliberations/{deliberation_id}")
async def get_deliberation(request: Request, deliberation_id: str) -> Deliberation:
    found = await _council(request).store.get_deliberation(deliberation_id)
    if found is None:
        raise HTTPException(status_code=404, detail="no such deliberation")
    return found


@router.get("/cards")
async def cards(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    status: CardStatus | None = Query(default=None),
) -> list[DecisionCard]:
    """Decision Cards, due ones first. `status`: open | due | resolved."""
    return await _council(request).store.list_cards(limit, status)


@router.get("/cards/{card_id}")
async def get_card(request: Request, card_id: str) -> DecisionCard:
    found = await _council(request).store.get_card(card_id)
    if found is None:
        raise HTTPException(status_code=404, detail="no such card")
    return found


@router.post("/cards/{card_id}/resolve")
async def resolve_card(
    request: Request,
    card_id: str,
    body: Resolution,
    grade: bool = Query(default=True, description="Also run the blind grader."),
) -> DecisionCard:
    """Record what actually happened, and score every module against it.

    This is the move that closes the loop. Until a card is resolved, nothing in the
    system learns anything — there is no ground truth about a real decision except
    what occurred.
    """
    try:
        return await _council(request).resolve(card_id, body, grade=grade)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="no such card") from exc
    except CognitiveOSError as exc:
        # The resolution is saved even when grading fails; re-grade with
        # POST /cards/{id}/grade rather than losing the outcome.
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/cards/{card_id}/grade")
async def grade_card(request: Request, card_id: str) -> DecisionCard:
    """Re-run the grader on an already-resolved card."""
    try:
        return await _council(request).grade(card_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="no such card") from exc
    except CognitiveOSError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.patch("/cards/{card_id}/verdict/{module}")
async def override_verdict(
    request: Request, card_id: str, module: str, body: VerdictOverride
) -> DecisionCard:
    """Replace the grader's verdict for one module. The human is the final judge."""
    try:
        return await _council(request).override_verdict(
            card_id, module, body.verdict, body.justification
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reminders")
async def reminders(request: Request) -> dict[str, object]:
    """Cards whose check-in date has arrived.

    A card schedules its own follow-up when it is written, so this needs no scheduler
    — but somebody has to ask. This endpoint, and the nudge the CLI prints, are that
    somebody.
    """
    due = await _council(request).store.list_cards(limit=100, status="due")
    return {
        "count": len(due),
        "message": (
            f"{len(due)} decision{'s' if len(due) != 1 else ''} due for a check-in. "
            "Recording what happened is what makes the council yours."
        )
        if due
        else "Nothing due.",
        "cards": [
            {
                "id": card.id,
                "question": card.question,
                "check_on": card.expected_outcome.check_on if card.expected_outcome else None,
                "expected": card.expected_outcome.statement if card.expected_outcome else None,
            }
            for card in due
        ],
    }


@router.post("/deliberations/{deliberation_id}/rerun")
async def rerun_stage(
    request: Request, deliberation_id: str, body: RerunRequest
) -> Deliberation:
    """Re-run one module from one stage, with new facts, then re-synthesise.

    Returns a **new** deliberation derived from the original. The original is never
    modified — the reasoning record is what Decision Cards get scored against, and
    editing it in place would destroy that (ADR-022).
    """
    try:
        return await _council(request).rerun_stage(
            deliberation_id,
            module=body.module,
            from_stage=body.from_stage,
            facts=body.facts,
            reason=body.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ProgramInvalid, CognitiveOSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/deliberations/{deliberation_id}/refine")
async def refine(request: Request, deliberation_id: str, body: RefineRequest) -> Deliberation:
    """Answer the council's open unknowns and deliberate again knowing them."""
    try:
        return await _council(request).refine(
            deliberation_id, answers=body.answers, reason=body.reason
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CognitiveOSError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/memories/{module}")
async def memories(
    request: Request, module: str, q: str = Query(default=""), k: int = Query(default=10, ge=1, le=50)
) -> list[dict[str, object]]:
    """What one module would recall for a query.

    Lexical overlap weighted by salience and recency, not embeddings — at a few
    hundred memories, vector search solves a problem that does not exist and misfires
    on shared vocabulary. Exposed so the retrieval is inspectable rather than magic.
    """
    found = await _council(request).store.recall(module, q, k)
    return [m.model_dump(mode="json") for m in found]


@router.get("/scores")
async def scores(
    request: Request, all_n: bool = Query(default=False, alias="all")
) -> dict[str, object]:
    """Per-module calibration.

    Nothing is shown below n=8 unless `all=true`. An accuracy figure over three
    decisions is not a measurement, and presenting one as though it were is the
    dishonest move this endpoint exists to avoid.
    """
    computed = await _council(request).store.scores()
    shown = computed if all_n else [s for s in computed if s.displayable]
    return {
        "min_n_to_display": MIN_N_TO_DISPLAY,
        "withheld": len(computed) - len(shown),
        "scores": [
            {**s.model_dump(), "overconfidence": s.overconfidence, "chance_brier": CHANCE_BRIER}
            for s in shown
        ],
    }


@router.get("/priors")
async def all_priors(request: Request) -> dict[str, list[Prior]]:
    """What each module will be told about this user on its next run."""
    store = _council(request).store
    cards = await store.list_cards(limit=500)
    return {
        module: [p.model_dump() for p in items]  # type: ignore[misc]
        for module, items in priors.build(cards).items()
    }


def _check_preset(name: str | None) -> None:
    if name is None:
        return
    try:
        loader.preset(name)
    except ProgramInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
