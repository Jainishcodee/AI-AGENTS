"""Does the checkpoint's bookkeeping tell the truth?

Every test here is about accounting rather than reasoning: whether a module is recorded
once, whether critique history survives, whether the reported cost is the real cost. That
sounds pedantic until you notice what consumes these numbers — the transcript, the trace,
the Decision Card, the divergence harness's critique yield, and the "calls already spent"
line a person reads before deciding whether to resume.

Two of these failures were introduced *by* the resumption work in Phase 4, which is the
argument for the file existing: banking partial work before re-raising an outage was the
right fix, and it silently double-counted every module that had succeeded.
"""

from __future__ import annotations

import pytest

from app.core.errors import ProviderError
from app.schemas.council import DeliberationRequest

from .conftest import QUESTION


class FailAt:
    """Fails once, at the Nth call, then behaves. A quota blip rather than a window."""

    def __init__(self, inner, at: int) -> None:
        self._inner = inner
        self._at = at
        self.calls = 0

    async def complete(self, role, request, *, override=None):
        self.calls += 1
        if self.calls == self._at:
            raise ProviderError("gemini", "HTTP 429: quota exhausted", retryable=False)
        return await self._inner.complete(role, request, override=override)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class FailRole:
    """Fails every call for one role.

    Aimed by role rather than by call index: counting calls to land on "the synthesis one"
    is guesswork, and a miss lands in the revision phase instead — where failures are
    caught and logged, so the test passes for the wrong reason or not at all.
    """

    def __init__(self, inner, role: str) -> None:
        self._inner = inner
        self._role = role
        self.blocked = 0

    async def complete(self, role, request, *, override=None):
        if role == self._role:
            self.blocked += 1
            raise ProviderError("gemini", "HTTP 429: quota exhausted", retryable=False)
        return await self._inner.complete(role, request, override=override)

    def __getattr__(self, name):
        return getattr(self._inner, name)


async def run(council, *, depth: str = "quick"):
    return await council.run(
        DeliberationRequest(question=QUESTION, depth=depth, preset="full")
    )


# ───────────────────────────────────────── every module recorded exactly once ──


async def test_a_module_is_recorded_once_per_deliberation(council):
    """The double-bank. `checkpoint.completed` was appended to in two separate loops.

    Nothing fails loudly: the deliberation looks complete, the recommendation is fine, and
    the duplication only shows up on *resume*, where `deliberation.runs` is seeded from
    `checkpoint.completed` and every module arrives twice.
    """
    deliberation = await run(council)
    modules = [r.module for r in deliberation.runs]
    assert len(modules) == len(set(modules)), f"duplicated runs: {sorted(modules)}"


async def test_the_checkpoint_records_each_module_once(council):
    """Checked on the checkpoint itself, because that is what a resume reads."""
    captured = {}
    original = council._checkpoint

    async def spy(checkpoint, live=None):
        captured["modules"] = [r.module for r in checkpoint.completed]
        captured["calls"] = checkpoint.usage.calls
        return await original(checkpoint, live)

    council._checkpoint = spy
    await run(council)

    modules = captured["modules"]
    assert len(modules) == len(set(modules)), f"checkpoint duplicated: {sorted(modules)}"


async def test_the_reported_cost_is_not_double_counted(council):
    """Usage was merged twice per module, so a run reported roughly twice its true cost.

    This is the number a person sees before deciding whether they can afford to continue,
    so an inflated one is worse than no number.
    """
    captured = {}
    original = council._checkpoint

    async def spy(checkpoint, live=None):
        captured["checkpoint_calls"] = checkpoint.usage.calls
        return await original(checkpoint, live)

    council._checkpoint = spy
    deliberation = await run(council)

    assert captured["checkpoint_calls"] <= deliberation.usage.calls, (
        f"checkpoint claims {captured['checkpoint_calls']} calls but the finished "
        f"deliberation only made {deliberation.usage.calls}"
    )


# ─────────────────────────────────────────────── critique history is preserved ──


async def test_a_deep_run_records_two_rounds_of_critique_not_three(council):
    """`deep` is two critique rounds; the extend from the checkpoint sat *inside* the loop.

    So round two replayed everything banked in round one on top of what the deliberation
    already held: two rounds of work, three rounds of critiques in the transcript.

    Asserted as a ratio against `standard` (one round) rather than by de-duplicating,
    because a second round legitimately re-critiques the same target — and the mock
    provider is deterministic, so its round-two text is genuinely identical to round one's.
    De-duplicating would call correct behaviour a bug.
    """
    standard = await run(council, depth="standard")
    deep = await run(council, depth="deep")

    assert standard.critiques, "no critiques at standard depth; the ratio means nothing"
    assert len(deep.critiques) == 2 * len(standard.critiques), (
        f"one round produced {len(standard.critiques)} critiques, so two rounds should "
        f"produce {2 * len(standard.critiques)} — the transcript has {len(deep.critiques)}"
    )
    assert len(deep.revisions) == 2 * len(standard.revisions), (
        f"expected {2 * len(standard.revisions)} revisions across two rounds, "
        f"got {len(deep.revisions)}"
    )


async def test_critique_history_survives_a_resume_into_synthesis(council):
    """The mirror-image bug: the extend was *only* inside the loop.

    Resuming with every critique round already done leaves the loop body unexecuted, so
    the banked critiques were never copied into the deliberation and vanished from the
    transcript — the run looked like nobody had critiqued anybody.
    """
    inner = council._router
    # Block only the synthesis call, so critique and revision run to completion and get
    # banked first. That is the state this test is about.
    blocked = FailRole(inner, "synthesis")
    council._router = blocked
    council._engine._router = blocked

    from app.core.errors import CognitiveOSError

    with pytest.raises((CognitiveOSError, ProviderError)):
        await run(council, depth="standard")
    assert blocked.blocked, "the synthesis call was never attempted"

    resumable = await council.resumable()
    assert resumable, "synthesis failure did not leave anything to resume"
    checkpoint = resumable[0]
    assert checkpoint.critiques, "critiques were not banked before synthesis"
    banked = len(checkpoint.critiques)

    # The window reopens.
    council._router = inner
    council._engine._router = inner

    from app.schemas.council import Deliberation

    resumed = None
    async for event in council.resume(checkpoint.deliberation_id):
        if event.type == "done":
            resumed = Deliberation.model_validate(event.payload["deliberation"])

    assert resumed is not None and resumed.synthesis is not None
    assert len(resumed.critiques) >= banked, (
        f"resumed transcript has {len(resumed.critiques)} critiques but "
        f"{banked} were banked — the critique history was dropped"
    )
    modules = [r.module for r in resumed.runs]
    assert len(modules) == len(set(modules)), (
        f"resume duplicated module runs: {sorted(modules)}"
    )


# ──────────────────────────────────────── a resume reuses the original program ──


async def test_a_fact_injected_before_the_crash_survives_the_resume(council):
    """`Checkpoint.injected` existed as a field and was never written to or read from.

    Injected facts are folded into the *local* context inside the executor, so they reached
    the modules running at the time and nothing else. Crash after injecting, resume, and the
    remaining modules are handed a context that never mentions the fact — the person
    answered the council's unknown and the resumed run behaves as though they had not.
    """
    from app.core.errors import CognitiveOSError
    from app.council.live import Injection
    from app.engine.executor import LATE_FACT_PREFIX
    from app.schemas.council import Deliberation

    inner = council._router
    fact = "The offer arrived in writing this morning, with a two-week deadline."

    # Inject as soon as the run is addressable, then let synthesis fail so the whole
    # reasoning phase is banked with the fact already consumed.
    blocked = FailRole(inner, "synthesis")
    council._router = blocked
    council._engine._router = blocked

    # Driven through the streaming path, because that is the only way to interject: it
    # reports failure as an `error` event rather than raising, so the checkpoint is the
    # thing to assert on.
    saw_checkpoint = False
    async for event in council.deliberate(
        DeliberationRequest(question=QUESTION, depth="quick", preset="full")
    ):
        if event.type == "run_started":
            live = council.live.get(event.payload["run_id"])
            assert live is not None
            await live.offer([Injection(fact=fact)])
        elif event.type == "checkpointed":
            saw_checkpoint = True
    assert saw_checkpoint, "the synthesis outage did not produce a checkpoint"

    resumable = await council.resumable()
    assert resumable, "nothing to resume"
    checkpoint = resumable[0]
    assert fact in checkpoint.injected, (
        "the injected fact was not recorded on the checkpoint, so a resume cannot know "
        "the person ever answered"
    )

    # The window reopens; capture what the resumed modules are actually told.
    council._router = inner
    council._engine._router = inner

    resumed = None
    async for event in council.resume(checkpoint.deliberation_id):
        if event.type == "done":
            resumed = Deliberation.model_validate(event.payload["deliberation"])

    assert resumed is not None
    constraints = " ".join(resumed.context.constraints)
    assert fact in constraints, "the resumed deliberation's context lost the injected fact"
    assert LATE_FACT_PREFIX in constraints, (
        "the fact must still be labelled as having arrived late — earlier stages "
        "genuinely did not have it"
    )
    assert constraints.count(fact) == 1, "the fact was folded in more than once"


async def test_a_resume_uses_the_preset_the_artifacts_were_built_against(council, settings):
    """`preset` and `depth` were re-resolved from the request, not read from the checkpoint.

    A request that did not name a preset falls back to the *current* default, so changing
    `COUNCIL_DEFAULT_PRESET` between the crash and the resume would continue a deliberation
    with a different set of modules than the banked artifacts came from. The same reasoning
    that stops intake being re-run applies here.
    """
    inner = council._router
    failing = FailAt(inner, at=3)
    council._router = failing
    council._engine._router = failing

    from app.core.errors import CognitiveOSError

    request = DeliberationRequest(question=QUESTION, depth="quick")  # no preset named
    with pytest.raises((CognitiveOSError, ProviderError)):
        await council.run(request)

    resumable = await council.resumable()
    assert resumable, "nothing to resume"
    checkpoint = resumable[0]
    original_preset = checkpoint.preset

    # The operator changes their default between the two attempts.
    council._settings = settings.model_copy(update={"default_preset": "people"})
    assert council._settings.default_preset != original_preset

    council._router = inner
    council._engine._router = inner

    from app.schemas.council import Deliberation

    resumed = None
    async for event in council.resume(checkpoint.deliberation_id):
        if event.type == "done":
            resumed = Deliberation.model_validate(event.payload["deliberation"])

    assert resumed is not None
    assert resumed.preset == original_preset, (
        f"resumed as '{resumed.preset}' but the artifacts were built for "
        f"'{original_preset}'"
    )
