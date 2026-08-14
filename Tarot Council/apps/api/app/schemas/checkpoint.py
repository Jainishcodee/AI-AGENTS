"""Resumable deliberations.

The reason this exists is the constraint ADR-020 identified: free tiers meter requests
per minute, so a `standard` full-council run is ~26 calls at 5 RPM — five minutes of wall
clock — and a `deep` run can outlive a quota window entirely. Before this, a run that died
at call 20 of 26 lost all twenty.

The unit of progress is the **artifact**, not the module. That is only affordable because
ADR-011 made every stage a separately validated artifact and the engine already accepts
`resume_from` + `seed`: a checkpoint stores partial module runs, and resuming re-enters
each module at its next unfinished stage rather than restarting it. A checkpoint write is
one SQLite upsert against an LLM call, so the bookkeeping is free in practice.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .common import ModuleId, Usage
from .council import (
    Critique,
    DecisionContext,
    DeliberationRequest,
    ModuleRun,
    Revision,
)

Phase = Literal["intake", "reason", "critique", "revise", "synthesis", "done"]

RESUMABLE_PHASES: frozenset[str] = frozenset({"reason", "critique", "revise", "synthesis"})
"""Phases worth resuming from.

`intake` is one cheap call — re-running it is cheaper than the bookkeeping to skip it.
`done` has nothing left to do.
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Checkpoint(BaseModel):
    """Everything needed to pick a deliberation back up where it stopped."""

    deliberation_id: str
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    request: DeliberationRequest
    """Kept verbatim so a resume reproduces the original run rather than a similar one."""

    preset: str
    depth: str
    project_id: str | None = None
    phase: Phase = "intake"
    context: DecisionContext | None = None

    completed: list[ModuleRun] = Field(default_factory=list)
    partial: dict[ModuleId, ModuleRun] = Field(default_factory=dict)
    """Modules that were mid-program. Their finished artifacts are kept, so resuming
    re-enters at the next stage instead of paying for the ones already done."""

    critiques: list[Critique] = Field(default_factory=list)
    revisions: list[Revision] = Field(default_factory=list)
    rounds_done: int = 0
    injected: list[str] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    failure: str | None = None
    """Why it stopped, when it stopped because something broke rather than being killed."""

    @property
    def resumable(self) -> bool:
        return self.phase in RESUMABLE_PHASES

    @property
    def artifacts_done(self) -> int:
        return sum(len(r.artifacts) for r in self.completed) + sum(
            len(r.artifacts) for r in self.partial.values()
        )

    def next_stage_for(self, module: ModuleId, stage_ids: list[str]) -> str | None:
        """The first stage this module has not produced yet.

        `None` means it finished, so resume should leave it alone.
        """
        run = self.partial.get(module)
        done = {a.stage_id for a in run.artifacts} if run else set()
        for stage_id in stage_ids:
            if stage_id not in done:
                return stage_id
        return None

    def describe(self) -> str:
        finished = [r.module for r in self.completed]
        started = sorted(self.partial)
        parts = [f"stopped in {self.phase}"]
        if finished:
            parts.append(f"{len(finished)} module(s) finished")
        if started:
            parts.append(f"{len(started)} part-way ({', '.join(started)})")
        parts.append(f"{self.usage.calls} calls already spent")
        return "; ".join(parts)
