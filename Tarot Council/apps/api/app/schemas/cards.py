"""Decision Cards and calibration.

The card is the unit of the product's memory. `expected_outcome` is written at
deliberation time, falsifiable, and dated — that is what makes later scoring a
prediction rather than hindsight.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .common import Confidence, MemoryKind, ModuleId, Verdict
from .council import Minority, Recommendation


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ExpectedOutcome(BaseModel):
    statement: str
    """Falsifiable and concrete. "It will go well" is rejected at synthesis."""
    check_on: date
    measurable_by: str = ""


class ModuleStance(BaseModel):
    module: ModuleId
    stance: str
    confidence: Confidence | None = None
    abstained: bool = False


class Resolution(BaseModel):
    chose: str
    """Free text, not an option id. People do not pick from the menu, and the rows
    where they chose something no module proposed are a direct measurement of the
    council's option-generation blindness."""
    actual_outcome: str
    happened_at: date
    surprises: list[str] = Field(default_factory=list)
    notes: str = ""


class DecisionCard(BaseModel):
    id: str
    user_id: str = "local"
    project_id: str | None = None
    created_at: datetime = Field(default_factory=_now)

    question: str
    deliberation_id: str
    preset: str
    depth: str
    program_versions: dict[ModuleId, int] = Field(default_factory=dict)

    recommendation: Recommendation
    per_module: list[ModuleStance] = Field(default_factory=list)
    expected_outcome: ExpectedOutcome | None = None
    minority_opinions: list[Minority] = Field(default_factory=list)

    resolution: Resolution | None = None
    scoring: dict[ModuleId, Verdict] = Field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return self.resolution is not None


class Memory(BaseModel):
    """One remembered item, extracted per module with its own bias."""

    id: str
    module: ModuleId
    kind: MemoryKind
    content: str
    salience: float = Field(default=0.5, ge=0.0, le=1.0)
    source_card_id: str | None = None
    created_at: datetime = Field(default_factory=_now)


class Prior(BaseModel):
    """A learned pattern injected as evidence, never as instruction (ADR-018)."""

    module: ModuleId
    pattern: str
    evidence_count: int = Field(ge=3)
    derived_from: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    domain: str | None = None


class AgentMemory(BaseModel):
    """Everything a module is handed beyond the DecisionContext."""

    recalled: list[Memory] = Field(default_factory=list)
    priors: list[Prior] = Field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.recalled and not self.priors


class ModuleScore(BaseModel):
    module: ModuleId
    domain: str | None = None
    n: int = 0
    brier: float | None = None
    hit_rate: float | None = None
    execution_rate: float | None = None
    horizon_days: int | None = None

    @property
    def displayable(self) -> bool:
        """Nothing is shown below n=8. An early number is a lie of presentation."""
        return self.n >= 8


CardStatus = Literal["open", "due", "resolved"]
