"""Program schema — an agent as an executable list of stages (ADR-011).

Mirrors docs/SPEC-FORMAT.md. The ten loader rules are enforced in
`programs/loader.py`, not here, because several need the artifact registry and
one needs the whole preset set.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import MemoryKind, ModuleId, StageId

CONTEXT_REF = "context"
MissingPolicy = Literal["ask", "mark_unknown", "infer_labelled", "abstain"]
Role = Literal["primary", "advisory", "critic"]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Skin(Frozen):
    """Presentation only. The engine never reads this (ADR-016)."""

    name: str
    title: str = ""
    accent: str = "#8a8a8a"


class InputSpec(Frozen):
    id: str
    description: str
    missing_policy: MissingPolicy = "mark_unknown"


class Inputs(Frozen):
    required: tuple[InputSpec, ...] = ()
    optional: tuple[InputSpec, ...] = ()


class NumericRange(Frozen):
    """`range` on a numeric column — the leaf-probability floor generalised."""

    column: str
    minimum: float | None = None
    maximum: float | None = None


class Coverage(Frozen):
    """`covers` — every value in an earlier stage's column must appear in this one.

    The generalisation of the psychologist's hardest invariant: every person named in the
    cast gets a profile, no partial sets and no skipping the awkward one. It is also the rule
    that makes a two-stage module more than two independent prompts, because it is checked
    across a stage boundary.
    """

    stage: StageId
    column: str
    """Column in *this* table holding the reference. Defaults to the same name."""
    into: str = ""


class SumRule(Frozen):
    """`sums_to` over a column, within a tolerance. Percentages and allocations."""

    column: str
    total: float = 1.0
    tolerance: float = 0.02


class TableSpec(Frozen):
    """Declarative invariants for an authored table (ADR-030).

    Not invented — *extracted*. Every rule here is a shape the hand-written validators in
    `engine/invariants.py` already assert for the built-in six, which is the argument that
    the vocabulary is expressive enough to hold an authored module to a real standard rather
    than a stylistic one:

        min_rows      OptionSet (>=7), FailureModeTable (>=3)
        required      the psychologist's nine dimensions, non-empty every time
        distinct      no two options may share a label
        required_tags REQUIRED_OPTION_TAGS; also ADR-014's forced `reckless` option
        ranges        the leaf-probability floor
        covers        PersonProfileSet must cover PersonList
        sums_to       probability-tree siblings, flattened to one column

    What it cannot express is stated in ADR-030 rather than hidden: recursive structures
    (tree depth, sibling sums over nesting) and cross-field semantics ("the ten-year regret
    must not contradict the one-year row"). Those stay hand-written, so an authored module is
    held to a weaker standard than the six — knowable and checkable, but weaker.
    """

    columns: tuple[str, ...] = ()
    min_rows: int = 1
    required: tuple[str, ...] = ()
    """Columns that must be present and non-empty in *every* row."""
    distinct: tuple[str, ...] = ()
    required_tags: tuple[str, ...] = ()
    """Each must be carried by at least one row."""
    ranges: tuple[NumericRange, ...] = ()
    covers: Coverage | None = None
    sums_to: SumRule | None = None


class Stage(Frozen):
    id: StageId
    name: str
    group: str
    reads: tuple[str, ...]
    produces: str
    instruction: str
    must_not: tuple[str, ...]
    terminal: bool = False
    min_items: int | None = None
    table: TableSpec | None = None
    """Required when `produces` is `Table`; forbidden otherwise."""
    isolate: bool = False
    """Never batched with a neighbour, at any depth.

    Set on stages whose value depends on not sharing context with the stage that
    follows — `tactician.generate` is the canonical case: divergence collapses the
    moment evaluation is in the same call.
    """


class Bias(Frozen):
    """Never shown to its owner (ADR-003)."""

    id: str
    description: str
    watch_for: str
    detectable_by: tuple[ModuleId, ...]


class SuccessMetric(Frozen):
    id: str
    question: str
    resolution: Literal["user_reported", "computed"] = "user_reported"
    horizon_days: int = Field(ge=1)


class Voice(Frozen):
    tone: str = ""
    forbidden: tuple[str, ...] = ()


class AgentProgram(Frozen):
    id: ModuleId
    version: int = 1
    skin: Skin
    summary: str
    inputs: Inputs = Inputs()
    mental_model: str
    stages: tuple[Stage, ...]
    biases: tuple[Bias, ...]
    critique_lens: str
    critics: tuple[ModuleId, ...]
    success_metrics: tuple[SuccessMetric, ...]
    risk_tolerance: float = Field(default=0.5, ge=0.0, le=1.0)
    time_horizon: Literal["short", "medium", "long"] = "medium"
    memory_kind: MemoryKind = "fact"
    voice: Voice = Voice()
    domain_weights: dict[str, float] = Field(default_factory=dict)
    veto_enabled: bool = False
    model_override: str | None = None

    @property
    def terminal_stage(self) -> Stage:
        return self.stages[-1]

    def stage(self, stage_id: StageId) -> Stage:
        for s in self.stages:
            if s.id == stage_id:
                return s
        raise KeyError(f"{self.id} has no stage {stage_id!r}")

    @property
    def groups(self) -> list[str]:
        """Group keys in declaration order, deduplicated."""
        seen: list[str] = []
        for s in self.stages:
            if s.group not in seen:
                seen.append(s.group)
        return seen


class Preset(Frozen):
    """Selects modules and assigns roles. Never modifies a program (ADR-017)."""

    id: str
    name: str
    description: str = ""
    primary: tuple[ModuleId, ...]
    advisory: tuple[ModuleId, ...] = ()
    critic: tuple[ModuleId, ...] = ()

    @property
    def running(self) -> tuple[ModuleId, ...]:
        """Modules that execute a full program."""
        return self.primary + self.advisory

    @property
    def participants(self) -> tuple[ModuleId, ...]:
        return self.primary + self.advisory + self.critic

    def role_of(self, module: ModuleId) -> Role:
        if module in self.primary:
            return "primary"
        if module in self.advisory:
            return "advisory"
        return "critic"
