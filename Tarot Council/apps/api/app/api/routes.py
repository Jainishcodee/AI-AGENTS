"""HTTP surface. Thin: validate, call the council, stream events."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..core.errors import CognitiveOSError, ProgramInvalid
from ..council import Council
from ..engine.planner import call_estimate
from ..programs import loader
from ..schemas.council import Deliberation, DeliberationRequest
from ..schemas.events import sse

router = APIRouter()


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
    found = await _council(request)._store.get_deliberation(deliberation_id)
    if found is None:
        raise HTTPException(status_code=404, detail="no such deliberation")
    return found


@router.get("/cards")
async def cards(request: Request, limit: int = Query(default=50, ge=1, le=200)):
    return await _council(request)._store.list_cards(limit)


def _check_preset(name: str | None) -> None:
    if name is None:
        return
    try:
        loader.preset(name)
    except ProgramInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
