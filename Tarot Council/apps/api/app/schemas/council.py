"""Council-level contracts: context, critique, revision, synthesis, deliberation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .artifacts import Artifact, Conclusion, Option
from .common import (
    ArtifactRowRef,
    Confidence,
    CritiqueKind,
    ModuleId,
    Reversibility,
    StageId,
    Strict,
    Usage,
)
from .program import Role


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════ intake ══


class DecisionContext(Strict):
    """Output of stage 0. Every module reads this and nothing else from outside."""

    question: str
    """Verbatim user text. Never paraphrased — the psychologist and ethicist must
    quote it, and a summary destroys the only evidence about the user's state."""

    normalised: str = ""
    domains: list[str] = Field(default_factory=list)
    decision_type: str = ""
    options: list[Option] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    current_state: str = ""
    time_box: str | None = None
    reversibility: Reversibility = "reversible"
    stated_values: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    is_decision: bool = True

    def named_entities(self) -> set[str]:
        """Everything the model is allowed to treat as a real named thing.

        Used by the no-fabricated-proper-nouns invariant.
        """
        out: set[str] = set()
        for a in self.actors:
            out.add(a.strip().lower())
        for o in self.options:
            out.add(o.label.strip().lower())
        return out


# ═════════════════════════════════════════════════════════════════ critique ══


class Critique(Strict):
    critic: ModuleId
    target: ModuleId
    target_ref: ArtifactRowRef | None = None
    kind: CritiqueKind
    statement: str
    severity: int = Field(default=3, ge=1, le=5)
    bias_id: str | None = None


class AcceptedCritique(Strict):
    from_module: ModuleId
    what: str
    how_it_changes_my_view: str


class RejectedCritique(Strict):
    from_module: ModuleId
    what: str
    why_rejected: str


class CritiqueItem(Strict):
    """What the model returns. `critic` is stamped server-side, not asked for."""

    target: ModuleId
    target_ref: ArtifactRowRef | None = None
    kind: CritiqueKind
    statement: str
    severity: int = Field(default=3, ge=1, le=5)
    bias_id: str | None = None


class CritiqueList(Strict):
    critiques: list[CritiqueItem] = Field(default_factory=list)


class RevisionDraft(Strict):
    """What the model returns for a revision; `module` is stamped server-side."""

    accepted: list["AcceptedCritique"] = Field(default_factory=list)
    rejected: list["RejectedCritique"] = Field(default_factory=list)
    stance: str
    confidence: Confidence
    delta: str = "unchanged"


class IntakeResult(Strict):
    """Stage 0 output. `question` is never asked for — it is the verbatim input."""

    normalised: str = ""
    domains: list[str] = Field(default_factory=list)
    decision_type: str = ""
    options: list[Option] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    current_state: str = ""
    time_box: str | None = None
    reversibility: Reversibility = "reversible"
    stated_values: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    is_decision: bool = True


class Revision(Strict):
    module: ModuleId
    accepted: list[AcceptedCritique] = Field(default_factory=list)
    rejected: list[RejectedCritique] = Field(default_factory=list)
    stance: str
    confidence: Confidence
    delta: str = "unchanged"


# ════════════════════════════════════════════════════════════════ synthesis ══


class ConsensusPoint(Strict):
    point: str
    modules: list[ModuleId] = Field(default_factory=list)
    supported_by: list[ArtifactRowRef] = Field(default_factory=list)


class Position(Strict):
    module: ModuleId
    position: str


class Disagreement(Strict):
    issue: str
    positions: list[Position] = Field(default_factory=list)
    why_it_matters: str
    what_would_resolve_it: str
    resolved_by: str | None = None


class FiredBias(Strict):
    bias_id: str
    module: ModuleId
    evidence: str
    corrected: bool = False


class Recommendation(Strict):
    action: str
    first_action: str
    timeline: str = ""
    do_not: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)


class Minority(Strict):
    module: ModuleId
    position: str
    when_it_would_be_right: str


class Alternative(Strict):
    action: str
    trigger: str


class Horizon(Strict):
    horizon: Literal["3mo", "1y", "5y"]
    prediction: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ExpectedOutcomeDraft(Strict):
    """Written at deliberation time, which is what makes it a prediction."""

    statement: str
    check_in_days: int = Field(default=90, ge=1, le=1095)
    measurable_by: str = ""


class Synthesis(Strict):
    debate_summary: str
    expected_outcome: ExpectedOutcomeDraft
    consensus: list[ConsensusPoint] = Field(default_factory=list)
    disagreements: list[Disagreement] = Field(default_factory=list)
    blind_spots_fired: list[FiredBias] = Field(default_factory=list)
    council_blind_spot: str
    recommendation: Recommendation
    confidence: Confidence
    calibration_note: str = ""
    ethical_veto_response: str | None = None
    minority_opinions: list[Minority] = Field(default_factory=list)
    alternative_strategy: Alternative | None = None
    long_term_prediction: list[Horizon] = Field(default_factory=list)
    information_to_gather: list[str] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════ results ══


class ModuleRun(BaseModel):
    """One module's execution record. The trace is derived from these."""

    module: ModuleId
    program_version: int
    role: Role
    artifacts: list[Artifact] = Field(default_factory=list)
    conclusion: Conclusion | None = None
    abstained: bool = False
    abstain_reason: str | None = None
    abstained_at: StageId | None = None
    usage: Usage = Field(default_factory=Usage)

    def artifact_at(self, stage_id: StageId) -> Artifact | None:
        for a in self.artifacts:
            if a.stage_id == stage_id:
                return a
        return None


class DeliberationRequest(BaseModel):
    question: str = Field(min_length=3)
    preset: str | None = None
    depth: Literal["quick", "standard", "deep"] | None = None
    context_notes: str = ""
    """Extra facts the user supplies up front — constraints, actors, values.
    Folded into the intake so modules do not have to ask for them."""


class Rerun(Strict):
    """Provenance for a derived deliberation.

    Re-running never mutates the original. The reasoning record *is* the product, and
    editing history in place would destroy the thing Decision Cards are scored
    against (ADR-022).
    """

    kind: Literal["stage", "refine"]
    module: ModuleId | None = None
    from_stage: StageId | None = None
    added_facts: list[str] = Field(default_factory=list)
    reason: str = ""


class Deliberation(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=_now)
    question: str
    preset: str
    depth: str
    derived_from: str | None = None
    rerun: Rerun | None = None
    context: DecisionContext
    runs: list[ModuleRun] = Field(default_factory=list)
    critiques: list[Critique] = Field(default_factory=list)
    revisions: list[Revision] = Field(default_factory=list)
    synthesis: Synthesis | None = None
    usage: Usage = Field(default_factory=Usage)
    program_versions: dict[ModuleId, int] = Field(default_factory=dict)

    def run_for(self, module: ModuleId) -> ModuleRun | None:
        for r in self.runs:
            if r.module == module:
                return r
        return None
