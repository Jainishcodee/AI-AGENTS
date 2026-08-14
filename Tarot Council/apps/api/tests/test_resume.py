"""Resumable deliberations (Phase 4).

The point is not crash-tolerance in the abstract. It is the constraint ADR-020 measured:
a `standard` run is ~26 calls at 5 requests a minute on a free tier, so a quota window or
a closed laptop ends one mid-flight. Before this, every call already paid for was lost.

The tests that matter are the ones that prove work is genuinely *reused* — a resume that
silently re-ran everything would pass a naive "did it finish" check while delivering
nothing.
"""

from __future__ import annotations

import pytest

from app.core.errors import CognitiveOSError, ProviderError
from app.programs import loader
from app.schemas.council import DeliberationRequest

from .conftest import QUESTION

FULL = DeliberationRequest(question=QUESTION, depth="quick", preset="full")


class FailAfter:
    """Wraps the router and dies after N calls, like a quota window closing."""

    def __init__(self, inner, limit: int) -> None:
        self._inner = inner
        self._limit = limit
        self.calls = 0
        self.tags: list[str] = []

    async def complete(self, role, request, *, override=None):
        if self.calls >= self._limit:
            raise ProviderError("gemini", "HTTP 429: quota exhausted", retryable=False)
        self.calls += 1
        self.tags.append(request.tag)
        return await self._inner.complete(role, request, override=override)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def install(council, limit: int) -> FailAfter:
    """Replace any existing wrapper rather than stacking on it.

    Wrapping an already-exhausted `FailAfter` would leave every call failing, which makes
    "the quota window reopened" tests pass for the wrong reason — a resume that did
    nothing would still look like it reused work.
    """
    inner = council._router
    while isinstance(inner, FailAfter):
        inner = inner._inner
    router = FailAfter(inner, limit)
    council._router = router
    council._engine._router = router
    return router


async def drain(council, request=FULL) -> list[str]:
    return [event.type async for event in council.deliberate(request)]


# ─────────────────────────────────────────────────── a run that dies banks ───


async def test_a_failed_run_leaves_a_resumable_checkpoint(council):
    install(council, limit=6)
    events = await drain(council)

    assert "error" in events
    assert "done" not in events
    assert "checkpointed" in events, "no checkpoint event was emitted"

    pending = await council.resumable()
    assert len(pending) == 1
    checkpoint = pending[0]
    assert checkpoint.resumable
    assert checkpoint.request.question == QUESTION
    assert checkpoint.context is not None, "intake was not banked"
    assert checkpoint.artifacts_done > 0, "no artifacts were banked"
    assert checkpoint.failure and "quota" in checkpoint.failure


async def test_a_completed_run_leaves_nothing_to_resume(council):
    events = await drain(council)
    assert "done" in events
    assert await council.resumable() == []


# ────────────────────────────────────────────── resuming reuses the work ─────


async def test_resuming_finishes_the_run_and_keeps_the_same_id(council):
    install(council, limit=8)
    await drain(council)
    checkpoint = (await council.resumable())[0]
    banked_id = checkpoint.deliberation_id

    # The quota window reopens.
    council._router = council._router._inner
    council._engine._router = council._router

    result = None
    async for event in council.resume(banked_id):
        if event.type == "done":
            from app.schemas.council import Deliberation

            result = Deliberation.model_validate(event.payload["deliberation"])

    assert result is not None
    assert result.id == banked_id, "a resume must continue the run, not start a lookalike"
    assert result.synthesis is not None
    assert {r.module for r in result.runs} == set(loader.programs())


async def test_resuming_does_not_pay_for_finished_stages_again(council):
    """The load-bearing test. A resume that re-ran everything would still 'work'."""
    first = install(council, limit=10)
    await drain(council)
    checkpoint = (await council.resumable())[0]

    banked_artifacts = checkpoint.artifacts_done
    assert banked_artifacts > 0

    second = install(council, limit=10_000)
    async for _event in council.resume(checkpoint.deliberation_id):
        pass

    # Whatever the resume spent, it must not have re-run the stages already banked.
    replayed = [
        tag
        for tag in second.tags
        for module in loader.programs()
        if tag.startswith(f"{module}:")
    ]
    total_stages = sum(len(loader.program(m).stages) for m in loader.programs())
    assert len(replayed) < total_stages, (
        f"the resume made {len(replayed)} module calls for {total_stages} stages — it "
        "looks like nothing was reused"
    )


async def test_a_module_that_finished_is_not_re_run_at_all(council):
    install(council, limit=12)
    await drain(council)
    checkpoint = (await council.resumable())[0]
    finished = {r.module for r in checkpoint.completed if not r.abstained}
    assert finished, "no module finished before the failure; widen the call limit"

    second = install(council, limit=10_000)
    async for _event in council.resume(checkpoint.deliberation_id):
        pass

    for module in finished:
        assert not any(tag.startswith(f"{module}:") for tag in second.tags), (
            f"{module} had already finished but was run again"
        )


async def test_usage_reports_the_true_cost_of_the_decision(council):
    """Not the cost of the last attempt — the cost of the decision."""
    first = install(council, limit=9)
    await drain(council)
    checkpoint = (await council.resumable())[0]
    spent_before = checkpoint.usage.calls

    second = install(council, limit=10_000)
    result = None
    async for event in council.resume(checkpoint.deliberation_id):
        if event.type == "done":
            from app.schemas.council import Deliberation

            result = Deliberation.model_validate(event.payload["deliberation"])

    assert result is not None
    assert result.usage.calls >= spent_before, (
        "the finished deliberation forgot what the first attempt already spent"
    )


async def test_the_checkpoint_is_cleared_once_the_run_completes(council):
    install(council, limit=8)
    await drain(council)
    checkpoint = (await council.resumable())[0]

    council._router = council._router._inner
    council._engine._router = council._router
    async for _event in council.resume(checkpoint.deliberation_id):
        pass

    assert await council.resumable() == []
    assert await council.store.get_checkpoint(checkpoint.deliberation_id) is None


# ───────────────────────────────────────────────────────── error handling ────


async def test_resuming_something_unknown_raises(council):
    with pytest.raises(KeyError):
        async for _event in council.resume("nope"):
            pass


async def test_discarding_a_checkpoint_removes_it(council):
    install(council, limit=6)
    await drain(council)
    checkpoint = (await council.resumable())[0]

    await council.discard(checkpoint.deliberation_id)
    assert await council.resumable() == []


async def test_checkpoint_survives_a_new_council_on_the_same_store(settings, tmp_path):
    """The whole promise: the process can die, not just the request."""
    from app.council import Council
    from app.memory.store import build_store

    settings.store_dir = tmp_path
    first = Council(settings, store=build_store("sqlite", tmp_path), force_provider="mock")
    try:
        install(first, limit=8)
        async for _event in first.deliberate(FULL):
            pass
        banked = (await first.resumable())[0].deliberation_id
    finally:
        await first.aclose()

    # A different process, same database.
    second = Council(settings, store=build_store("sqlite", tmp_path), force_provider="mock")
    try:
        pending = await second.resumable()
        assert [c.deliberation_id for c in pending] == [banked]
        assert pending[0].artifacts_done > 0

        result = None
        async for event in second.resume(banked):
            if event.type == "done":
                from app.schemas.council import Deliberation

                result = Deliberation.model_validate(event.payload["deliberation"])
        assert result is not None and result.id == banked
    finally:
        await second.aclose()


async def test_describe_is_useful_enough_to_decide_on(council):
    install(council, limit=10)
    await drain(council)
    detail = (await council.resumable())[0].describe()
    assert "stopped in" in detail
    assert "calls already spent" in detail
