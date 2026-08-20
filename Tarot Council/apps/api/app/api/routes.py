"""HTTP surface. Thin: validate, call the council, stream events."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from ..core.errors import CognitiveOSError, ProgramInvalid
from ..council import Council
from ..council.live import Injection
from ..engine.planner import call_estimate
from ..learning import divergence, priors
from ..learning.scoring import CHANCE_BRIER
from ..programs import catalog, loader
from ..reminders import ics
from ..schemas.cards import (
    MIN_N_TO_DISPLAY,
    CardStatus,
    DecisionCard,
    Prior,
    Project,
    ReplayResult,
    Resolution,
)
from ..schemas.common import Verdict
from ..schemas.divergence import StructuralReport
from ..schemas.module import ModuleCatalogEntry, ModuleStatus, UserModule
from ..schemas.program import AgentProgram
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


class InjectRequest(BaseModel):
    facts: list[str] = Field(min_length=1)
    answers_gap: str | None = None


class ProjectRequest(BaseModel):
    name: str = Field(min_length=1)
    brief: str = ""


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
    await _check_preset(council, body.preset)

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
    council = _council(request)
    await _check_preset(council, body.preset)
    try:
        return await council.run(body)
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


@router.get("/council/live")
async def live_runs(request: Request) -> list[dict[str, object]]:
    """Deliberations currently executing, and what has been injected into each."""
    return [
        {
            "run_id": run.run_id,
            "question": run.question,
            "pending": [i.fact for i in run.pending],
            "applied": run.facts,
        }
        for run in _council(request).live.active()
    ]


@router.post("/council/live/{run_id}/inject")
async def inject(request: Request, run_id: str, body: InjectRequest) -> dict[str, object]:
    """Supply a fact to a deliberation that is still running.

    Every batch that has not yet started picks it up; batches already in flight are
    left alone, so a stage's output is always explicable by the context it was handed.
    Facts arriving this way are labelled as late in the transcript rather than merged
    silently — earlier stages genuinely did not have them.
    """
    try:
        count = await _council(request).live.inject(
            run_id, [Injection(fact=f, answers_gap=body.answers_gap) for f in body.facts]
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=(
                f"no live run '{run_id}'. It may have finished — use "
                f"POST /deliberations/{{id}}/refine to answer unknowns after the fact."
            ),
        ) from exc
    return {"run_id": run_id, "queued": count}


@router.get("/council/resumable")
async def resumable(request: Request) -> list[dict[str, object]]:
    """Deliberations that stopped part-way and still have work banked.

    The common cause is not a crash: on a free tier a `standard` run is ~26 calls at 5
    requests a minute, so a quota window or a closed laptop ends one mid-flight (ADR-020).
    """
    return [
        {
            "deliberation_id": c.deliberation_id,
            "question": c.request.question,
            "phase": c.phase,
            "artifacts_done": c.artifacts_done,
            "calls_spent": c.usage.calls,
            "updated_at": c.updated_at,
            "failure": c.failure,
            "detail": c.describe(),
        }
        for c in await _council(request).resumable()
    ]


@router.post("/council/resumable/{deliberation_id}/resume")
async def resume(request: Request, deliberation_id: str) -> StreamingResponse:
    """Continue where it stopped, reusing every artifact already paid for.

    Streams the same event types as a fresh deliberation — one code path, so a resumed
    run cannot drift from a normal one.
    """
    council = _council(request)

    # Checked *before* the StreamingResponse is returned. `council.resume` is an async
    # generator, so its body — and its "no such deliberation" — does not run until the
    # first iteration, which happens after the status line has already gone out as 200.
    # Resuming a nonexistent id would look like success and then hand back a broken stream.
    checkpoint = await council.store.get_checkpoint(deliberation_id)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail="no such resumable deliberation")
    if not checkpoint.resumable:
        raise HTTPException(
            status_code=409,
            detail=f"deliberation stopped in '{checkpoint.phase}', which is not resumable",
        )

    async def stream() -> AsyncIterator[str]:
        async for event in council.resume(deliberation_id):
            yield sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


@router.delete("/council/resumable/{deliberation_id}")
async def discard_checkpoint(request: Request, deliberation_id: str) -> dict[str, str]:
    await _council(request).discard(deliberation_id)
    return {"discarded": deliberation_id}


@router.get("/catalog")
async def module_catalog(request: Request) -> list[ModuleCatalogEntry]:
    """Every module, built-in or authored, including quarantined ones with their errors.

    One list rather than two, so no client has to branch on origin to show what exists —
    and a broken module is visible rather than mysteriously absent (ADR-030).
    """
    return await _council(request).modules()


@router.get("/catalog/{module_id}")
async def get_user_module(request: Request, module_id: str) -> UserModule:
    found = await _council(request).store.get_module(module_id)
    if found is None:
        raise HTTPException(status_code=404, detail="no such authored module")
    return found


@router.put("/catalog/{module_id}")
async def put_user_module(
    request: Request, module_id: str, program: AgentProgram
) -> UserModule:
    """Create or replace an authored module.

    Returns **200 with the verdict attached** rather than 422 on a rule violation, because
    saving a broken draft is the normal state of authoring and refusing the write would
    leave the author nothing to iterate on. Read `status` and `errors`: a quarantined module
    is stored and listed but cannot run.
    """
    if program.id != module_id:
        raise HTTPException(
            status_code=400,
            detail=f"program id '{program.id}' does not match the path '{module_id}'",
        )
    council = _council(request)
    existing = await council.store.get_module(module_id)
    # Through `catalog.author` so the shared constitution is merged exactly as it is for the
    # CLI and for built-ins. Building the `UserModule` here by hand was the bug: rule 10 then
    # fired on every request and this route could never store a valid module.
    return await council.save_module(catalog.author(module_id, program, existing=existing))


class StatusChange(BaseModel):
    status: ModuleStatus


@router.post("/catalog/{module_id}/status")
async def set_module_status(
    request: Request, module_id: str, body: StatusChange
) -> UserModule:
    """Put a module into play, or withdraw it. Re-validated on the way in."""
    try:
        return await _council(request).set_module_status(module_id, body.status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="no such authored module") from exc
    except CognitiveOSError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/catalog/{module_id}")
async def delete_user_module(request: Request, module_id: str) -> dict[str, str]:
    await _council(request).delete_module(module_id)
    return {"deleted": module_id}


@router.get("/divergence")
async def divergence_structural() -> StructuralReport:
    """Do these modules actually represent problems differently?

    Reads only the specs, so it is instant. Artifact distinctness and critique topology
    are properties of the YAML: a module producing no artifact type that nothing else
    produces will converge with its twin however differently it is phrased (ADR-002), and
    a module nobody critiques can never have its declared biases caught (ADR-003).

    The live half — dissent rate, critique yield, stance similarity over a battery of
    real decisions — needs a model and minutes, so it lives on the CLI
    (`app.cli divergence --live`) rather than behind a web request.
    """
    return divergence.structural()


@router.get("/projects")
async def projects(request: Request) -> list[Project]:
    """Ongoing situations, open ones first."""
    return await _council(request).store.list_projects()


@router.post("/projects")
async def create_project(request: Request, body: ProjectRequest) -> Project:
    return await _council(request).create_project(body.name, body.brief)


@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: str) -> dict[str, object]:
    store = _council(request).store
    project = await store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="no such project")
    lister = getattr(store, "cards_in_project", None)
    cards = (
        await lister(project_id)
        if lister
        else [c for c in await store.list_cards(limit=500) if c.project_id == project_id]
    )
    return {"project": project, "cards": cards}


@router.post("/projects/{project_id}/close")
async def close_project(request: Request, project_id: str) -> Project:
    try:
        return await _council(request).close_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="no such project") from exc


@router.post("/cards/{card_id}/replay")
async def replay_card(request: Request, card_id: str) -> ReplayResult:
    """Re-decide a resolved card against today's programs and grade it against what
    actually happened.

    Turns the resolved corpus into a test set for the council itself. Memories and
    priors derived from this card are withheld for the duration — otherwise a module
    reads its own answer — and the response reports how many were withheld (ADR-025).
    """
    try:
        return await _council(request).replay(card_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="no such card") from exc
    except CognitiveOSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/calendar.ics")
async def calendar_feed(request: Request) -> Response:
    """Every open check-in as an iCalendar feed (ADR-031).

    The one reminder channel that reaches the user when the app is closed, the laptop is
    shut and the API is down — because the calendar app already syncs to their phone. A
    subscription only auto-refreshes if this URL is reachable by the calendar provider, which
    a localhost API is not; `python -m app.cli calendar` writes the same document to a file
    for the offline case, and the README says so rather than implying otherwise.
    """
    cards = await _council(request).store.list_cards(limit=500)
    document = ics.render(ics.build(cards))
    return Response(
        content=document,
        media_type="text/calendar; charset=utf-8",
        headers={"content-disposition": 'inline; filename="decision-checkins.ics"'},
    )


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


async def _check_preset(council: Council, name: str | None) -> None:
    """Reject a bad preset before the stream opens, authored modules included.

    Resolved through the catalog rather than the loader: `loader.preset` knows only the
    built-in six, so it rejected every `with:<authored module>` name with a 400 and made
    authored modules unreachable over HTTP entirely — the orchestrator would have run them
    perfectly well. Same class of mistake as validating inside a `StreamingResponse`: the
    check has to know as much as the thing it is guarding.
    """
    if name is None:
        return
    try:
        catalog.preset(name, await council.store.list_modules())
    except ProgramInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
