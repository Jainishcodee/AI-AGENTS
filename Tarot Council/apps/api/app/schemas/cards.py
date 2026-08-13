"""Decision Cards and calibration.

The card is the unit of the product's memory. `expected_outcome` is written at
deliberation time, falsifiable, and dated — that is what makes later scoring a
prediction rather than hindsight.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .common import Confidence, MemoryKind, ModuleId, Strict, Verdict
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
    role: str = "primary"
    """A module's accuracy in `critic` role is not comparable to `primary`
    (ADR-017), so the role it held is recorded alongside the stance."""


Verdict_ = Verdict  # re-export alias, keeps the import surface stable


class ModuleVerdict(BaseModel):
    """How one module's stance fared. Produced by the grader, overridable by hand."""

    module: ModuleId
    verdict: Verdict
    justification: str = ""
    followed: bool = False
    """Did the user actually act on this module's stance? A module with a high hit
    rate on the 10% of advice the user was willing to take is not performing well —
    it is advising a different person."""
    falsifier_fired: bool = False
    """Did the specific observation the module named as disqualifying occur? The
    fastest honest signal in the system: checkable in days, not months."""
    overridden: bool = False
    """True when a human replaced the grader's verdict."""


class MetricAnswer(BaseModel):
    """An answer to one of a module's own declared `success_metrics`."""

    module: ModuleId
    metric_id: str
    answer: Literal["yes", "no", "unclear"]
    evidence: str = ""


class CardScoring(BaseModel):
    graded_at: datetime = Field(default_factory=_now)
    expected_outcome_met: Literal["yes", "no", "partial", "unclear"] = "unclear"
    chose_was_proposed: bool = True
    """False when the user did something no module put on the table — a direct
    measurement of the council's option-generation blindness."""
    module_verdicts: list[ModuleVerdict] = Field(default_factory=list)
    metric_answers: list[MetricAnswer] = Field(default_factory=list)
    unpredicted: list[str] = Field(default_factory=list)
    grader_model: str = ""

    def verdict_for(self, module: ModuleId) -> ModuleVerdict | None:
        for verdict in self.module_verdicts:
            if verdict.module == module:
                return verdict
        return None


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
    domains: list[str] = Field(default_factory=list)
    """Carried from the intake so accuracy can be computed per domain — the
    strategist may be strong on negotiation and weak on money, and one number
    across both would hide it."""
    program_versions: dict[ModuleId, int] = Field(default_factory=dict)

    recommendation: Recommendation
    per_module: list[ModuleStance] = Field(default_factory=list)
    expected_outcome: ExpectedOutcome | None = None
    minority_opinions: list[Minority] = Field(default_factory=list)

    resolution: Resolution | None = None
    scoring: CardScoring | None = None

    @property
    def resolved(self) -> bool:
        return self.resolution is not None

    @property
    def graded(self) -> bool:
        return self.scoring is not None and bool(self.scoring.module_verdicts)

    def is_due(self, today: date) -> bool:
        return (
            not self.resolved
            and self.expected_outcome is not None
            and self.expected_outcome.check_on <= today
        )

    def status(self, today: date) -> "CardStatus":
        if self.resolved:
            return "resolved"
        return "due" if self.is_due(today) else "open"


class Project(BaseModel):
    """An ongoing situation that several decisions belong to.

    Real decisions arrive in chains — "should I leave", then "how do I negotiate",
    then "do I take the counteroffer". Grouping them is what stops recall from
    dragging memories about a side project into a conversation about a salary.
    """

    id: str
    user_id: str = "local"
    name: str
    brief: str = ""
    created_at: datetime = Field(default_factory=_now)
    closed_at: datetime | None = None

    @property
    def open(self) -> bool:
        return self.closed_at is None


class Memory(BaseModel):
    """One remembered item, extracted per module with its own bias."""

    id: str
    module: ModuleId
    kind: MemoryKind
    content: str
    salience: float = Field(default=0.5, ge=0.0, le=1.0)
    source_card_id: str | None = None
    project_id: str | None = None
    """Inherited from the card it came from, so recall can prefer same-project
    memories over merely similar-sounding ones."""
    created_at: datetime = Field(default_factory=_now)


class MemoryDraft(Strict):
    module: ModuleId
    kind: MemoryKind
    content: str
    salience: float = Field(default=0.5, ge=0.0, le=1.0)


class ExtractionResult(Strict):
    """One call, six extraction rules.

    Splitting into six calls would be more faithful to "six memories with six
    biases", but the rules are distinct enough stated side by side that the extra
    five calls buy little — and on a per-minute quota they cost a lot (ADR-020).
    """

    memories: list[MemoryDraft] = Field(default_factory=list)


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


class ModuleReplay(Strict):
    """How one module did the first time versus on a replay."""

    module: ModuleId
    then_stance: str = ""
    now_stance: str = ""
    then_verdict: Verdict | None = None
    now_verdict: Verdict | None = None
    then_confidence: float | None = None
    now_confidence: float | None = None

    @property
    def moved(self) -> bool:
        return self.then_verdict != self.now_verdict


class ReplayResult(BaseModel):
    """A resolved decision re-run against the current programs.

    The point of the exercise: with the outcome already known, re-running an old
    decision measures whether a changed program would have done better — the only way
    to improve the council on evidence rather than on taste.
    """

    card_id: str
    original_deliberation_id: str
    replay_deliberation_id: str
    program_versions_then: dict[ModuleId, int] = Field(default_factory=dict)
    program_versions_now: dict[ModuleId, int] = Field(default_factory=dict)
    modules: list[ModuleReplay] = Field(default_factory=list)
    excluded_memories: int = 0
    excluded_priors: int = 0
    """What was withheld to stop the replay reading its own answer (ADR-025)."""

    @property
    def improved(self) -> int:
        rank = {"wrong": 0, "untested": 1, "partial": 2, "right": 3}
        return sum(
            1
            for m in self.modules
            if m.then_verdict
            and m.now_verdict
            and rank[m.now_verdict] > rank[m.then_verdict]
        )

    @property
    def regressed(self) -> int:
        rank = {"wrong": 0, "untested": 1, "partial": 2, "right": 3}
        return sum(
            1
            for m in self.modules
            if m.then_verdict
            and m.now_verdict
            and rank[m.now_verdict] < rank[m.then_verdict]
        )


class ModuleScore(BaseModel):
    module: ModuleId
    domain: str | None = None
    n: int = 0
    """Scored, non-`untested` decisions. Not the number of deliberations."""
    brier: float | None = None
    """Mean squared error of stated confidence against outcome. Lower is better;
    0.25 is what you get by always saying 50%."""
    hit_rate: float | None = None
    mean_confidence: float | None = None
    execution_rate: float | None = None
    falsifier_hit_rate: float | None = None
    horizon_days: int | None = None

    @property
    def overconfidence(self) -> float | None:
        """Stated confidence minus what actually happened. Positive = overconfident."""
        if self.mean_confidence is None or self.hit_rate is None:
            return None
        return round(self.mean_confidence - self.hit_rate, 3)

    @property
    def displayable(self) -> bool:
        """Nothing is shown below n=8. An early number is a lie of presentation."""
        return self.n >= MIN_N_TO_DISPLAY


MIN_N_TO_DISPLAY = 8
MIN_N_FOR_PRIOR = 3
"""A prior needs three data points. Two is an anecdote, and an anecdote injected as
a prior is how a system becomes confidently wrong about one specific person."""

CardStatus = Literal["open", "due", "resolved"]


# ─────────────────────────────────────────────────── what the grader returns ──


class ModuleVerdictDraft(Strict):
    module: ModuleId
    verdict: Verdict
    justification: str
    followed: bool = False
    falsifier_fired: bool = False


class MetricAnswerDraft(Strict):
    module: ModuleId
    metric_id: str
    answer: Literal["yes", "no", "unclear"]
    evidence: str = ""


class GraderResult(Strict):
    """Judged blind: the grader is never shown any module's stated confidence.

    Otherwise "this module was 85% sure" leaks into whether it is marked right, and
    the Brier score becomes circular. Calibration is computed afterwards, in code,
    from the confidence stored on the card (ADR-021).
    """

    expected_outcome_met: Literal["yes", "no", "partial", "unclear"]
    chose_was_proposed: bool
    module_verdicts: list[ModuleVerdictDraft] = Field(min_length=1)
    metric_answers: list[MetricAnswerDraft] = Field(default_factory=list)
    unpredicted: list[str] = Field(default_factory=list)
