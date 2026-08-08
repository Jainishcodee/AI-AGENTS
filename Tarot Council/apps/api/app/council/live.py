"""Mid-deliberation interjection.

A deliberation raises unknowns as it goes — `EvidenceGaps`, `missing_inputs`, an actor
nobody named. Answering those *after* the fact is `refine` (ADR-022). Answering them
*while modules are still running* is this: facts arrive on a channel, and every batch
that has not yet started picks them up.

The interesting result is what this did **not** need. The obvious design is
checkpointing — persist execution state, halt, resume — which is the case ADR-007
reserved for LangGraph. But injection never leaves the process: a running deliberation
is a live async generator, and the only thing required is a place to put facts and a
check before each batch. So the registry below is a dict of queues, and the engine hook
is four lines.

That moves the LangGraph decision again. It earns its place when execution must survive
the process — a deliberation you close your laptop on and resume tomorrow — not merely
when a human interrupts one.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ..core.logging import get_logger

log = get_logger(__name__)


@dataclass
class Injection:
    """One fact supplied while the council was still thinking."""

    fact: str
    answers_gap: str | None = None
    """The unknown this responds to, when the caller knows it."""


@dataclass
class LiveRun:
    """A deliberation currently executing, and the facts queued for it."""

    run_id: str
    question: str
    pending: list[Injection] = field(default_factory=list)
    consumed: list[Injection] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def offer(self, injections: list[Injection]) -> None:
        async with self._lock:
            self.pending.extend(injections)

    async def drain(self) -> list[Injection]:
        """Take everything queued. Called before each batch starts.

        Draining rather than peeking means a fact is merged into the context exactly
        once, and `consumed` keeps the record of which stages could have seen it — the
        transcript should show when knowledge arrived, not just that it did.
        """
        async with self._lock:
            if not self.pending:
                return []
            taken, self.pending = self.pending, []
            self.consumed.extend(taken)
            return taken

    @property
    def facts(self) -> list[str]:
        return [item.fact for item in self.consumed]


class LiveRegistry:
    """The set of deliberations currently in flight.

    In-process and deliberately not persisted: a run that outlives the process cannot
    be injected into anyway, so persisting the registry would advertise a capability
    that does not exist.
    """

    def __init__(self) -> None:
        self._runs: dict[str, LiveRun] = {}

    def open(self, run_id: str, question: str) -> LiveRun:
        run = LiveRun(run_id=run_id, question=question)
        self._runs[run_id] = run
        return run

    def close(self, run_id: str) -> None:
        self._runs.pop(run_id, None)

    def get(self, run_id: str) -> LiveRun | None:
        return self._runs.get(run_id)

    def active(self) -> list[LiveRun]:
        return list(self._runs.values())

    async def inject(self, run_id: str, facts: list[Injection]) -> int:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        await run.offer(facts)
        log.info("%d fact(s) injected into live run %s", len(facts), run_id)
        return len(facts)
