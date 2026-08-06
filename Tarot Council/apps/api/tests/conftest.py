from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.council import Council  # noqa: E402
from app.memory.store import InMemoryStore  # noqa: E402
from app.schemas.council import DecisionContext  # noqa: E402

QUESTION = (
    "Should I quit my internship to work on my own product? My manager keeps promising "
    "a full-time offer but nothing is in writing, and I have four months of savings. "
    "I care about not burning the bridge."
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        COUNCIL_MAX_CONCURRENCY=8,
        COUNCIL_MAX_RPM=0,
        COUNCIL_MAX_RETRIES=0,
        COUNCIL_STORE="memory",
        COUNCIL_LOG_LEVEL="WARNING",
    )


@pytest.fixture
def context() -> DecisionContext:
    return DecisionContext(
        question=QUESTION,
        normalised="whether to leave the internship now or wait for the written offer",
        domains=["career"],
        actors=["my manager"],
        constraints=["four months of savings"],
        current_state="interning while building a product on the side",
        stated_values=["not burning the bridge"],
    )


@pytest.fixture
async def council(settings: Settings):
    instance = Council(settings, store=InMemoryStore(), force_provider="mock")
    try:
        yield instance
    finally:
        await instance.aclose()


class RecordingRouter:
    """Wraps a Router and records every (tag, system, user) triple it is asked for.

    Used by the isolation test: the guarantee that no module can see another's
    reasoning in stage 1 is structural, and this is how we prove it holds in the
    rendered prompts rather than merely in the call signature.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls: list[tuple[str, str, str]] = []

    async def complete(self, role, request, *, override=None):
        self.calls.append((request.tag, request.system, request.user))
        return await self._inner.complete(role, request, override=override)

    def __getattr__(self, name):
        return getattr(self._inner, name)
