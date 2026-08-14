"""Divergence measurement — does a module actually think differently?

The product's central claim is that these are six algorithms, not six voices. That claim
is falsifiable, and this is the instrument. It is also the gate a Phase 5 marketplace
module has to pass: "sounds different" is not a contribution.

Two halves, deliberately separated by cost:

- `StructuralReport` needs no model at all. Artifact distinctness and critique topology
  are properties of the specs, so they are computable instantly and can be asserted in
  CI on every commit.
- `LiveReport` needs a real council run over a battery of decisions. It is opt-in,
  because on a free tier it costs minutes and quota.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .common import ModuleId, Strict

MIN_DISSENTS = 2
"""A module must oppose the recommendation on at least this many battery decisions.

From SPEC-FORMAT.md. A module that never dissents is not contributing a perspective —
it is agreeing in a different accent."""

MIN_ACCEPTED_CRITIQUES = 1
"""At least one critique it raised must be accepted by another module. Attacks nobody
concedes to are noise, however confidently phrased."""

MAX_STANCE_SIMILARITY = 0.6
"""Mean pairwise word overlap between its stance and the others'.

Crude on purpose: it is a floor, not a judgement. Its job is to catch the degenerate
case where every module returns near-identical text — which is precisely the failure
this whole architecture exists to prevent, and which no amount of prompt craft would
reveal from reading one output."""


class ModuleStructure(Strict):
    module: ModuleId
    unique_artifacts: list[str] = Field(default_factory=list)
    """Artifact kinds only this module produces. Its representational contribution."""
    shared_artifacts: list[str] = Field(default_factory=list)
    critiques: list[ModuleId] = Field(default_factory=list)
    critiqued_by: list[ModuleId] = Field(default_factory=list)
    biases_detected_elsewhere: int = 0

    @property
    def distinct(self) -> bool:
        """Does it represent the problem in a way nothing else does?

        The threshold is one unique artifact type. Two modules that produce exactly the
        same artifacts over the same entities will converge no matter how their prompts
        read (ADR-002), so this is the cheapest real test of a new module.
        """
        return bool(self.unique_artifacts)


class StructuralReport(Strict):
    modules: list[ModuleStructure] = Field(default_factory=list)
    artifact_owners: dict[str, list[ModuleId]] = Field(default_factory=dict)
    problems: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


class ModuleDivergence(Strict):
    module: ModuleId
    decisions: int = 0
    dissents: int = 0
    """Battery decisions where it appeared in `minority_opinions` — i.e. it opposed the
    council's own recommendation."""
    disagreements: int = 0
    """Decisions where the synthesiser named it in an explicit disagreement."""
    critiques_raised: int = 0
    critiques_accepted: int = 0
    stance_similarity: float | None = None
    abstentions: int = 0
    problems: list[str] = Field(default_factory=list)

    @property
    def passes(self) -> bool:
        return not self.problems


class LiveReport(Strict):
    battery: list[str] = Field(default_factory=list)
    modules: list[ModuleDivergence] = Field(default_factory=list)
    mean_stance_similarity: float | None = None
    decisions_with_no_disagreement: int = 0
    """The council-level red flag. Six fixed algorithms should not agree unanimously on
    a battery chosen to have tradeoffs; if they do, either the battery is too easy or the
    modules have collapsed into one voice."""
    notes: list[str] = Field(default_factory=list)

    @property
    def failing(self) -> list[ModuleId]:
        return [m.module for m in self.modules if not m.passes]


class BatteryItem(BaseModel):
    """One decision in the fixed battery, with enough context that nobody abstains."""

    id: str
    question: str
    notes: str = ""
    domains: list[str] = Field(default_factory=list)
