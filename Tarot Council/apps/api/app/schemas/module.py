"""User-authored modules (Phase 5).

A user module is *the same* `AgentProgram` the engine already executes — this file adds
provenance and a status, not a second program format. There is no parallel interpreter and
no separate execution path, which is the whole reason ADR-011's "an agent is a program"
framing was worth the effort: the marketplace is a storage and validation problem, not an
engine problem.

The one genuinely new idea is **quarantine**. A built-in program that breaks a SPEC-FORMAT
rule refuses to let the server start, and that loudness is correct for a developer error. It
is wrong for user content: a half-finished draft is the normal state of authoring, and a
draft that prevents the server booting takes away the only tool for fixing it. So a user
module carries its own validation verdict (ADR-030).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .common import ModuleId
from .program import AgentProgram

ModuleStatus = Literal["draft", "active", "quarantined", "retired"]

MODULE_STATUSES: tuple[str, ...] = ("draft", "active", "quarantined", "retired")
"""The same set as `ModuleStatus`, available at runtime.

A `Literal` cannot be checked with `in`, and `model_copy(update=...)` does not re-validate —
so without this, a caller passing an unknown status wrote it to the store verbatim and every
`status == "active"` comparison silently disagreed with it. `tests/test_user_modules.py`
asserts the two stay in step.
"""
"""
- `draft` — authored, never yet run. Excluded from presets by the author's intent.
- `active` — valid and eligible to run.
- `quarantined` — saved but breaks at least one rule. Excluded, with the errors kept so the
  author can see what to fix. Never fatal.
- `retired` — deliberately withdrawn. Kept rather than deleted, because deliberations that
  already ran cite its version and the trace must stay explicable.
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserModule(BaseModel):
    """A stored, versioned, user-authored program plus the verdict on it."""

    id: ModuleId
    program: AgentProgram
    status: ModuleStatus = "draft"
    errors: list[str] = Field(default_factory=list)
    """SPEC-FORMAT violations from the last save. Non-empty implies `quarantined`."""

    author: str = "local"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    based_on: ModuleId | None = None
    """Set when forked from another module, so lineage survives independent editing."""

    notes: str = ""

    @property
    def runnable(self) -> bool:
        return self.status == "active" and not self.errors

    def describe(self) -> str:
        if self.errors:
            return f"{self.status}: {len(self.errors)} rule violation(s)"
        return f"{self.status}: {len(self.program.stages)} stages"


class ModuleCatalogEntry(BaseModel):
    """One row of the catalog — built-in or authored, uniformly described.

    Exists so the API and UI never have to branch on origin to list what is available. The
    `origin` field is informational; `runnable` is the field that decides anything.
    """

    id: ModuleId
    origin: Literal["builtin", "user"]
    status: ModuleStatus
    runnable: bool
    summary: str
    stages: int
    errors: list[str] = Field(default_factory=list)
