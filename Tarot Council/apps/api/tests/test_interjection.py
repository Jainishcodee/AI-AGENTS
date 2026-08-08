"""Mid-deliberation interjection (Phase 4).

Answering an unknown *while the council is still thinking*. The interesting property
being asserted is the boundary: a fact reaches every batch that has not started, and
never changes the inputs of one already in flight — a stage's artifact must always be
explicable by the context it was handed.
"""

from __future__ import annotations

import asyncio

import pytest

from app.council.live import Injection, LiveRegistry
from app.engine.executor import LATE_FACT_PREFIX
from app.programs import loader
from app.schemas.council import DeliberationRequest

from .conftest import QUESTION

LATE_FACT = "The investor confirmed in writing that the title is a non-event"


class InjectingRouter:
    """Injects a fact the instant a named stage's call returns.

    Reacting to the event stream instead would be a race: `emit` queues events without
    waiting for the consumer, and the mock model answers in microseconds, so a whole
    program finishes before a test loop can respond. Injecting from inside the router
    puts the fact between two batches deterministically — which is exactly where a
    human injection lands in a real 60-second deliberation.
    """

    def __init__(self, inner, registry, after_stage: str, fact: str = LATE_FACT) -> None:
        self._inner = inner
        self._registry = registry
        self._after = after_stage
        self._fact = fact
        self.calls: list[tuple[str, str, str]] = []
        self.injected_after: list[str] = []

    async def complete(self, role, request, *, override=None):
        self.calls.append((request.tag, request.system, request.user))
        response = await self._inner.complete(role, request, override=override)
        _module, _, batch = request.tag.partition(":")
        if self._after in batch.split("+"):
            active = self._registry.active()
            if active:
                await active[0].offer([Injection(fact=self._fact)])
                self.injected_after.append(batch)
        return response

    def __getattr__(self, name):
        return getattr(self._inner, name)


def install(council, after_stage: str) -> InjectingRouter:
    router = InjectingRouter(council._router, council.live, after_stage)
    council._router = router
    council._engine._router = router
    return router


# ─────────────────────────────────────────────────────────── the registry ───


async def test_registry_opens_closes_and_lists():
    registry = LiveRegistry()
    run = registry.open("r1", "a question")
    assert registry.get("r1") is run
    assert [r.run_id for r in registry.active()] == ["r1"]
    registry.close("r1")
    assert registry.get("r1") is None
    assert registry.active() == []


async def test_injecting_into_an_unknown_run_raises():
    with pytest.raises(KeyError):
        await LiveRegistry().inject("nope", [Injection(fact="x")])


async def test_draining_moves_pending_to_consumed_exactly_once():
    registry = LiveRegistry()
    run = registry.open("r1", "q")
    await registry.inject("r1", [Injection(fact="a"), Injection(fact="b")])

    first = await run.drain()
    assert [i.fact for i in first] == ["a", "b"]
    assert run.pending == []
    assert run.facts == ["a", "b"]

    # A second drain yields nothing: a fact is merged into the context once.
    assert await run.drain() == []
    assert run.facts == ["a", "b"]


async def test_concurrent_injection_and_drain_lose_nothing():
    """The queue is touched from the request handler and the engine at once."""
    registry = LiveRegistry()
    run = registry.open("r1", "q")

    async def writer(start: int) -> None:
        for index in range(20):
            await registry.inject("r1", [Injection(fact=f"f{start + index}")])
            await asyncio.sleep(0)

    drained: list[str] = []

    async def reader() -> None:
        for _ in range(60):
            drained.extend(i.fact for i in await run.drain())
            await asyncio.sleep(0)

    await asyncio.gather(writer(0), writer(100), reader())
    drained.extend(i.fact for i in await run.drain())
    assert len(drained) == 40
    assert len(set(drained)) == 40, "a fact was delivered twice"


# ─────────────────────────────────────────────── end to end in a council ────


async def test_a_fact_injected_mid_run_reaches_later_stages_only(council):
    """The boundary: later batches see it, earlier ones cannot have."""
    stage_ids = [s.id for s in loader.program("strategist").stages]
    router = install(council, after_stage="graph")

    await council.run(
        DeliberationRequest(question=QUESTION, depth="deep", preset="solo:strategist")
    )
    assert router.injected_after == ["graph"], "the injection point was never reached"

    seen_by = {
        tag.split(":", 1)[1]: user
        for tag, _system, user in router.calls
        if tag.startswith("strategist:")
    }
    cut = stage_ids.index("graph")

    for stage_id in stage_ids[: cut + 1]:
        assert LATE_FACT not in seen_by.get(stage_id, ""), (
            f"{stage_id} ran before the fact arrived and must not contain it"
        )
    later = [s for s in stage_ids[cut + 1 :] if s in seen_by]
    assert later, "no stage ran after the injection"
    assert all(LATE_FACT in seen_by[s] for s in later), (
        "every stage after the injection should carry the fact"
    )


async def test_late_facts_are_labelled_as_late(council):
    """A module must not treat late information as though it was always there."""
    router = install(council, after_stage="frame")
    await council.run(
        DeliberationRequest(question=QUESTION, depth="deep", preset="solo:analyst")
    )
    tagged = [u for tag, _s, u in router.calls if tag.startswith("analyst:") and LATE_FACT in u]
    assert tagged
    assert all(LATE_FACT_PREFIX in prompt for prompt in tagged)


async def test_an_injection_emits_an_event_naming_the_next_stage(council):
    install(council, after_stage="audit_waste")
    applied: list[dict] = []

    async for event in council.deliberate(
        DeliberationRequest(question=QUESTION, depth="deep", preset="solo:optimizer")
    ):
        if event.type == "injection_applied":
            applied.append(event.payload)

    assert applied, "no injection_applied event was emitted"
    assert applied[0]["facts"] == [LATE_FACT]
    assert applied[0]["before_stage"] == "constraint", (
        "the event should name the first stage that actually saw the fact"
    )


async def test_the_run_is_addressable_from_the_first_event(council):
    """A client must be able to inject as soon as it sees an unknown raised."""
    events = []
    async for event in council.deliberate(
        DeliberationRequest(question=QUESTION, depth="quick", preset="solo:analyst")
    ):
        events.append(event.type)
        if event.type == "run_started":
            assert council.live.get(event.payload["run_id"]) is not None
    assert events[0] == "run_started"


async def test_the_live_run_is_closed_when_the_deliberation_ends(council):
    run_ids: list[str] = []
    async for event in council.deliberate(
        DeliberationRequest(question=QUESTION, depth="quick", preset="solo:analyst")
    ):
        if event.type == "run_started":
            run_ids.append(event.payload["run_id"])
    assert run_ids
    assert council.live.get(run_ids[0]) is None
    assert council.live.active() == []


async def test_injected_facts_are_recorded_on_the_transcript(council):
    """The record should say when knowledge arrived, not merely that it did."""
    install(council, after_stage="frame")
    result = await council.run(
        DeliberationRequest(question=QUESTION, depth="deep", preset="solo:analyst")
    )

    assert result.rerun is not None
    assert result.rerun.kind == "refine"
    assert LATE_FACT in result.rerun.added_facts
    assert "mid-deliberation" in result.rerun.reason


async def test_a_run_with_no_injections_records_nothing(council):
    result = await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="solo:analyst")
    )
    assert result.rerun is None
