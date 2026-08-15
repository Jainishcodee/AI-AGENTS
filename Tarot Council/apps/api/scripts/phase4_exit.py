"""Phase 4's exit criterion, demonstrated across two separate processes.

`tests/test_resume.py` proves resumption in-process, which is not the same claim. ADR-027
says the point of checkpointing is that *execution survives the process* — so this script
runs as two invocations against one SQLite file:

    python -m scripts.phase4_exit crash     # quota dies mid-deliberation; checkpoint saved
    python -m scripts.phase4_exit resume     # a NEW process picks it up and finishes

It asserts the two things that matter: the resumed run reaches a synthesis, and no module
re-answers a stage it had already completed. Mock provider, so it costs nothing.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.errors import (  # noqa: E402
    CognitiveOSError,
    ProviderError,
    ProviderUnavailable,
)
from app.council import Council  # noqa: E402
from app.schemas.council import Deliberation, DeliberationRequest  # noqa: E402

QUESTION = "Should I take the smaller offer with equity?"
LEDGER = Path(__file__).parent / "phase4_exit.json"


class QuotaWindow:
    """Dies after N calls, like a free-tier window closing mid-run."""

    def __init__(self, inner, limit: int) -> None:
        self._inner = inner
        self._limit = limit
        self.calls = 0

    async def complete(self, role, request, *, override=None):
        if self.calls >= self._limit:
            raise ProviderError("gemini", "HTTP 429: quota exhausted", retryable=False)
        self.calls += 1
        return await self._inner.complete(role, request, override=override)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _fingerprint(run) -> dict[str, str]:
    """`stage/kind` → hash of the payload.

    Hashing rather than listing, because "the module did not re-answer" is a claim about
    the *content*: a stage that silently re-ran and produced something new would still
    show up under the same name.
    """
    return {
        f"{artifact.stage_id}/{artifact.kind}": hashlib.sha256(
            json.dumps(artifact.data, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        for artifact in run.artifacts
    }


def _council() -> Council:
    # No store override: this must go through the real on-disk SQLite store, since the
    # whole point is that the checkpoint outlives the process.
    return Council(get_settings(), force_provider="mock")


async def crash() -> int:
    council = _council()
    router = QuotaWindow(council._router, limit=14)
    council._router = router
    council._engine._router = router
    try:
        request = DeliberationRequest(question=QUESTION, depth="quick", preset="full")
        try:
            await council.run(request)
        # `run()` collects the stream, so the outage arrives as a CognitiveOSError carrying
        # the provider message rather than as ProviderUnavailable itself.
        except (ProviderUnavailable, CognitiveOSError) as exc:
            print(f"quota closed mid-run: {exc}")
        else:
            print("FAIL: the deliberation completed; the quota never ran out")
            return 1

        resumable = await council.resumable()
        if not resumable:
            print("FAIL: nothing was checkpointed")
            return 1

        checkpoint = resumable[0]
        banked = {run.module: _fingerprint(run) for run in checkpoint.completed}
        partial = {module: _fingerprint(run) for module, run in checkpoint.partial.items()}
        LEDGER.write_text(
            json.dumps(
                {
                    "id": checkpoint.deliberation_id,
                    "phase": checkpoint.phase,
                    "completed": banked,
                    "partial": partial,
                    "calls_before_crash": router.calls,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"crashed after {router.calls} calls, in phase '{checkpoint.phase}'")
        print(f"  checkpoint {checkpoint.deliberation_id}")
        print(f"  {len(banked)} module(s) complete, {len(partial)} partial")
        for module, artifacts in {**banked, **partial}.items():
            print(f"    {module}: {len(artifacts)} artifact(s) banked")
        return 0
    finally:
        await council.aclose()


async def resume() -> int:
    if not LEDGER.exists():
        print("FAIL: run `crash` first")
        return 1
    before = json.loads(LEDGER.read_text(encoding="utf-8"))

    council = _council()
    router = QuotaWindow(council._router, limit=10_000)  # the window reopened
    council._router = router
    council._engine._router = router
    try:
        resumable = await council.resumable()
        match = [c for c in resumable if c.deliberation_id == before["id"]]
        if not match:
            print(f"FAIL: checkpoint {before['id']} did not survive the process")
            return 1

        print(f"a new process found checkpoint {before['id']} on disk")

        # `resume` streams events, same as `deliberate`; the finished deliberation arrives
        # on `done`.
        deliberation = None
        async for event in council.resume(before["id"]):
            if event.type == "done":
                deliberation = Deliberation.model_validate(event.payload["deliberation"])
            elif event.type == "error" and not event.payload.get("recoverable"):
                print(f"FAIL: {event.payload.get('message')}")
                return 1

        if deliberation is None:
            print("FAIL: the resumed stream never produced a deliberation")
            return 1
        if deliberation.synthesis is None:
            print("FAIL: the resumed deliberation produced no synthesis")
            return 1

        # No module may re-answer a stage it had already completed: every banked artifact
        # must reappear in the finished run with a byte-identical payload.
        finished = {run.module: _fingerprint(run) for run in deliberation.runs}
        carried = 0
        for module, banked in before["completed"].items():
            after = finished.get(module)
            if after is None:
                print(f"FAIL: {module} was banked but is missing from the result")
                return 1
            for key, digest in banked.items():
                if key not in after:
                    print(f"FAIL: {module} lost a banked artifact on resume: {key}")
                    return 1
                if after[key] != digest:
                    print(f"FAIL: {module} re-answered {key} instead of reusing it")
                    return 1
                carried += 1

        abstained = [run.module for run in deliberation.runs if run.abstained]
        print(f"resumed and synthesised. {len(deliberation.runs)} runs, {router.calls} new calls")
        print(
            f"  {carried} banked artifact(s) from {len(before['completed'])} module(s) "
            "carried through byte-identically"
        )
        print(f"  abstentions: {abstained or 'none'}")
        print(f"  recommendation: {deliberation.synthesis.recommendation.action[:70]}")
        if abstained:
            print("FAIL: a resumed module abstained; the outage leaked into the result")
            return 1

        await council.discard(before["id"])
        LEDGER.unlink(missing_ok=True)
        print("\nPhase 4 exit criterion met, across two processes.")
        return 0
    finally:
        await council.aclose()


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "crash"
    raise SystemExit(asyncio.run({"crash": crash, "resume": resume}[step]()))
