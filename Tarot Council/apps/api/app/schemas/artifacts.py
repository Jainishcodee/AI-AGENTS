"""Artifact models — the authority on what may exist in a reasoning trace.

Mirrors docs/ARTIFACTS.md. Every type here needs an invariant validator in
`engine/invariants.py`; the program loader refuses a program producing a type
missing either half.

The `Artifact` envelope carries `data` as a plain dict rather than a discriminated
union. That is deliberate: it keeps `engine/` a genuine interpreter — it looks
types up in `ARTIFACT_MODELS` and never imports a specific artifact — and it makes
persistence and streaming trivial. `Artifact.typed()` recovers the model.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .common import (
    ArtifactRowRef,
    Confidence,
    CostToResolve,
    EdgeKind,
    EvidenceStatus,
    ModuleId,
    OptionTag,
    Reversibility,
    SourceQuality,
    StageId,
    Strict,
    ValueSource,
    WasteVerdict,
)


class ArtifactData(Strict):
    """Base for every artifact payload.

    `notes` is capped at two sentences by an invariant. Uncapped, it becomes the
    field where models hide the answer they were told not to give yet — but it is
    genuinely needed, because several invariants let a strong claim ("nothing here
    is wasteful") pass only if it is stated explicitly rather than implied by an
    empty table.
    """

    notes: str | None = None


# ═══════════════════════════════════════════════════════════════════ analyst ══


class Option(Strict):
    id: str
    label: str
    description: str = ""


class DecisionFrame(ArtifactData):
    options: list[Option] = Field(min_length=1)
    the_actual_choice: str
    time_box: str | None = None
    reversibility: Reversibility = "reversible"
    success_criteria: list[str] = Field(default_factory=list)


class EvidenceRow(Strict):
    id: str
    statement: str
    status: EvidenceStatus
    source: str = ""
    load_bearing: bool = False
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class EvidenceLedger(ArtifactData):
    rows: list[EvidenceRow] = Field(min_length=1)


class Gap(Strict):
    id: str
    question: str
    why_it_matters: str
    would_change_decision: bool = False
    cost_to_resolve: CostToResolve = "cheap"
    how_to_resolve: str = ""


class EvidenceGaps(ArtifactData):
    rows: list[Gap] = Field(default_factory=list)


class BaseRate(Strict):
    id: str
    reference_class: str
    observed_rate: str
    applicability: float = Field(ge=0.0, le=1.0)
    source_quality: SourceQuality


class BaseRateTable(ArtifactData):
    rows: list[BaseRate] = Field(default_factory=list)


class Outcome(Strict):
    description: str
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    magnitude: int = Field(default=3, ge=1, le=5)


class TreeNode(Strict):
    id: str
    label: str
    probability: float | None = Field(default=None, ge=0.0, le=1.0)
    condition: str | None = None
    outcome: Outcome | None = None
    children: list["TreeNode"] = Field(default_factory=list)


TreeNode.model_rebuild()


class ProbabilityTree(ArtifactData):
    root: TreeNode


class FailureMode(Strict):
    id: str
    scenario: str
    trigger: str
    probability: float = Field(default=0.2, ge=0.0, le=1.0)
    severity: int = Field(default=3, ge=1, le=5)
    early_warning_signal: str
    mitigation: str = ""


class FailureModeTable(ArtifactData):
    rows: list[FailureMode] = Field(default_factory=list)


# ═════════════════════════════════════════════════════════════════ tactician ══


class Misread(Strict):
    actor: str
    thinks_the_game_is: str


class InfoAsymmetry(Strict):
    holder: str
    what_they_know: str
    exploitable: bool = False


class TempoRead(Strict):
    who_is_under_pressure: str
    whose_clock_is_running: str
    if_i_wait: str = ""


class SituationRead(ArtifactData):
    game_being_played: str
    who_thinks_otherwise: list[Misread] = Field(default_factory=list)
    information_asymmetries: list[InfoAsymmetry] = Field(default_factory=list)
    tempo: TempoRead


class GeneratedOption(Strict):
    id: str
    label: str
    description: str = ""
    tags: list[OptionTag] = Field(default_factory=list)


class OptionSet(ArtifactData):
    options: list[GeneratedOption] = Field(min_length=1)


class AsymmetryRow(Strict):
    option_id: str
    max_downside: str
    realistic_upside: str
    downside_cost: int = Field(ge=1, le=5)
    upside_value: int = Field(ge=1, le=5)
    ratio: float = 0.0
    reversibility: Reversibility = "reversible"
    time_to_know: str = ""


class AsymmetryTable(ArtifactData):
    rows: list[AsymmetryRow] = Field(default_factory=list)


class RankedRow(Strict):
    option_id: str
    rank: int = Field(ge=1)
    rationale: str = ""
    score: float = 0.0


class DroppedRow(Strict):
    option_id: str
    why: str


class RankedOptions(ArtifactData):
    ranking: list[RankedRow] = Field(default_factory=list)
    dropped: list[DroppedRow] = Field(default_factory=list)


class EthicsCheck(Strict):
    """The influence boundary, as a gate (ADR-009).

    All three booleans must be false or the artifact is rejected.
    """

    uses_deception: bool = True
    manufactures_urgency: bool = True
    exploits_crisis: bool = True
    rationale: str = ""


class UnexpectedMove(ArtifactData):
    move: str
    why_available: str
    what_it_forces: str
    cost_if_wrong: str = ""
    ethics_check: EthicsCheck


class Reaction(Strict):
    actor: str
    my_move: str
    their_likely_response: str
    probability: float = Field(default=0.5, ge=0.0, le=1.0)
    my_counter: str
    tempo_effect: str = ""


class ReactionForecast(ArtifactData):
    rows: list[Reaction] = Field(default_factory=list)


# ════════════════════════════════════════════════════════════════ strategist ══


class Actor(Strict):
    id: str
    label: str
    role: str = ""
    is_user: bool = False
    inferred: bool = False


class ActorList(ArtifactData):
    actors: list[Actor] = Field(min_length=1)


class GraphNode(Strict):
    id: str
    label: str
    role: str = ""
    formal_authority: float = Field(default=0.5, ge=0.0, le=1.0)
    real_influence: float = Field(default=0.5, ge=0.0, le=1.0)
    controls: list[str] = Field(default_factory=list)
    fears: list[str] = Field(default_factory=list)
    optimising_for: str = ""
    stated_position: str | None = None
    actual_interest: str | None = None
    # Set server-side, never by the model: |authority - influence| >= 0.4.
    power_gap: bool = False


class GraphEdge(Strict):
    src: str
    dst: str
    kind: EdgeKind
    weight: float = Field(default=0.5, ge=0.0, le=1.0)
    is_hidden: bool = False
    note: str = ""


class StakeholderGraph(ArtifactData):
    nodes: list[GraphNode] = Field(min_length=1)
    edges: list[GraphEdge] = Field(default_factory=list)


class Incentive(Strict):
    actor_id: str
    rewarded_for: str
    punished_for: str = ""
    will_never_say: str
    misalignment_with_me: str = ""
    severity: int = Field(default=3, ge=1, le=5)


class IncentiveTable(ArtifactData):
    rows: list[Incentive] = Field(default_factory=list)


class Leverage(Strict):
    id: str
    what: str
    who_wants_it: str
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    expiry: str


class Batna(Strict):
    actor_id: str = "me"
    description: str
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    honest_assessment: str = ""


class LeverageInventory(ArtifactData):
    i_control: list[Leverage] = Field(default_factory=list)
    my_batna: Batna
    their_batna: list[Batna] = Field(default_factory=list)


class Debt(Strict):
    who_owes: str
    owed_to: str
    for_what: str
    callable_now: bool = False


class Alliance(Strict):
    members: list[str]
    basis: str
    stability: float = Field(default=0.5, ge=0.0, le=1.0)


class Shift(Strict):
    event: str
    when: str
    who_gains: str
    who_loses: str


class HiddenDynamics(ArtifactData):
    debts: list[Debt] = Field(default_factory=list)
    alliances: list[Alliance] = Field(default_factory=list)
    upcoming_shifts: list[Shift] = Field(default_factory=list)
    confidence: float = Field(default=0.4, ge=0.0, le=1.0)


class SequenceStep(Strict):
    order: int = Field(ge=1)
    actor_id: str
    objective: str
    must_yield_before_next: str = ""
    if_it_fails: str
    commit_point: bool = False


class SequencePlan(ArtifactData):
    steps: list[SequenceStep] = Field(min_length=1)


# ══════════════════════════════════════════════════════════════ psychologist ══


class Person(Strict):
    id: str
    label: str
    relationship_to_user: str = ""
    is_user: bool = False
    inferred: bool = False


class PersonList(ArtifactData):
    people: list[Person] = Field(min_length=1)


class PersonProfile(Strict):
    """The nine dimensions. Every person, every time — no partial profiles."""

    person_id: str
    driving_emotion: str
    fear: str
    unmet_need: str
    motivation: str
    stress_level: int = Field(ge=1, le=5)
    reaction_if_accepted: str
    reaction_if_rejected: str
    what_they_wont_say: str
    confidence: float = Field(ge=0.0, le=1.0)


class PersonProfileSet(ArtifactData):
    profiles: list[PersonProfile] = Field(min_length=1)


class SelfRead(ArtifactData):
    stated_feeling: str
    likely_real_feeling: str
    evidence_from_phrasing: list[str] = Field(default_factory=list)
    what_is_being_avoided: str
    question_behind_the_question: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RelationEdge(Strict):
    a: str
    b: str
    dynamic: str
    tension: int = Field(default=0, ge=0, le=5)
    who_holds_emotional_leverage: str | None = None


class RelationshipEdges(ArtifactData):
    edges: list[RelationEdge] = Field(default_factory=list)


class Script(Strict):
    person_id: str
    goal: str
    opening: str
    likely_objection: str = ""
    response: str = ""
    what_not_to_say: str = ""


class ConversationScripts(ArtifactData):
    scripts: list[Script] = Field(default_factory=list)


class PersonCost(Strict):
    person_id: str
    cost: int = Field(ge=0, le=5)


class CostRow(Strict):
    option_id: str
    cost_to_me: int = Field(ge=0, le=5)
    cost_to_others: list[PersonCost] = Field(default_factory=list)
    recovery_time: str = ""


class EmotionalCostTable(ArtifactData):
    rows: list[CostRow] = Field(default_factory=list)


# ═════════════════════════════════════════════════════════════════ optimizer ══


class OutcomeDefinition(ArtifactData):
    outcome: str
    metric: str
    deadline: str | None = None
    how_we_would_know: str


class WasteRow(Strict):
    id: str
    activity: str
    cost: str
    outcome_produced: str
    verdict: WasteVerdict
    rationale: str = ""


class WasteAudit(ArtifactData):
    rows: list[WasteRow] = Field(default_factory=list)


class NonConstraint(Strict):
    what: str
    why_it_looks_binding: str


class ConstraintAnalysis(ArtifactData):
    binding_constraint: str
    evidence: list[str] = Field(default_factory=list)
    if_relieved: str
    non_constraints: list[NonConstraint] = Field(default_factory=list)


class Baseline(Strict):
    what_happens: str
    cost: str = ""
    acceptable: bool = False


class SimplestPath(ArtifactData):
    do_nothing_baseline: Baseline
    simplest_sufficient: str
    one_tenth_time_version: str
    what_gets_dropped: list[str] = Field(default_factory=list)


class ErRow(Strict):
    option_id: str
    effort: int = Field(ge=1, le=5)
    expected_return: int = Field(ge=1, le=5)
    ratio: float = 0.0
    simpler_version: str | None = None


class EffortReturnRanking(ArtifactData):
    rows: list[ErRow] = Field(default_factory=list)


class SystemDesign(ArtifactData):
    rule: str
    trigger: str
    automation: str | None = None
    maintenance_cost: str


# ══════════════════════════════════════════════════════════════════ ethicist ══


class Party(Strict):
    id: str
    label: str
    in_the_room: bool = True
    can_consent: bool = True
    future_self: bool = False
    inferred: bool = False


class AffectedParties(ArtifactData):
    parties: list[Party] = Field(min_length=1)


class ValueRow(Strict):
    id: str
    value: str
    source: ValueSource
    quote: str | None = None
    options_serving: list[str] = Field(default_factory=list)
    options_violating: list[str] = Field(default_factory=list)


class ValueAudit(ArtifactData):
    rows: list[ValueRow] = Field(default_factory=list)


class HarmRow(Strict):
    option_id: str
    who_pays: list[str] = Field(default_factory=list)
    magnitude: int = Field(default=0, ge=0, le=5)
    reversible: bool = True
    consented: bool = False
    alternative_that_avoids: str | None = None


class HarmLedger(ArtifactData):
    rows: list[HarmRow] = Field(default_factory=list)


class RegretRow(Strict):
    option_id: str
    regret_1y: int = Field(ge=0, le=5)
    regret_5y: int = Field(ge=0, le=5)
    regret_10y: int = Field(ge=0, le=5)
    tell_a_friend_test: str = ""
    asymmetry: str = ""


class RegretMatrix(ArtifactData):
    rows: list[RegretRow] = Field(default_factory=list)


class Becoming(Strict):
    option_id: str
    what_kind_of_person: str
    acceptable: bool = True


class Promise(Strict):
    to_whom: str
    what: str
    renegotiable: bool = True


class IntegrityCheck(ArtifactData):
    requires_becoming: list[Becoming] = Field(default_factory=list)
    promises_broken: list[Promise] = Field(default_factory=list)


class InactionHarm(ArtifactData):
    """Mandatory counterweight to the ethicist's paralysis bias (ADR-014)."""

    harm_of_delay: str
    harm_of_status_quo: str
    who_pays_for_inaction: list[str] = Field(min_length=1)
    decay: str


# ══════════════════════════════════════════════════════════ shared terminal ══


class Conclusion(ArtifactData):
    """The only artifact type with a stance field. Terminal stages only."""

    stance: str
    first_action: str
    reasoning: str
    key_claims: list[ArtifactRowRef] = Field(default_factory=list)
    confidence: Confidence
    what_would_change_my_mind: str = ""
    cheapest_decisive_test: str | None = None
    ethical_veto: bool = False
    veto_grounds: str | None = None


# ══════════════════════════════════════════════════════ authored artifacts ══


class TableRow(Strict):
    """One row of an authored table.

    `cells` is an open mapping rather than named fields because the columns are declared by
    the module's author, not here — the *shape* is checked against the stage's `TableSpec`
    at validation time (ADR-030). This is the one place in the artifact registry where the
    Pydantic model is deliberately looser than the thing it validates, and the declarative
    rules are what close that gap.
    """

    id: str
    cells: dict[str, str | float | int | bool | None] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class Table(ArtifactData):
    """The artifact kind an authored module produces.

    Deliberately generic and deliberately *not* freeform: a module declares its columns and
    its constraints, and the engine enforces them. A table with no declared rules would be a
    persona with a prompt, which is the thing loader rule 4 exists to prevent — so the
    loader refuses a stage that produces `Table` without a `TableSpec`.
    """

    title: str = ""
    rows: list[TableRow] = Field(default_factory=list)


# ═════════════════════════════════════════════════════════════════ registry ══

ARTIFACT_MODELS: dict[str, type[ArtifactData]] = {
    m.__name__: m
    for m in (
        DecisionFrame,
        EvidenceLedger,
        EvidenceGaps,
        BaseRateTable,
        ProbabilityTree,
        FailureModeTable,
        SituationRead,
        OptionSet,
        AsymmetryTable,
        RankedOptions,
        UnexpectedMove,
        ReactionForecast,
        ActorList,
        StakeholderGraph,
        IncentiveTable,
        LeverageInventory,
        HiddenDynamics,
        SequencePlan,
        PersonList,
        PersonProfileSet,
        SelfRead,
        RelationshipEdges,
        ConversationScripts,
        EmotionalCostTable,
        OutcomeDefinition,
        WasteAudit,
        ConstraintAnalysis,
        SimplestPath,
        EffortReturnRanking,
        SystemDesign,
        AffectedParties,
        ValueAudit,
        HarmLedger,
        RegretMatrix,
        IntegrityCheck,
        InactionHarm,
        Table,
        Conclusion,
    )
}

TERMINAL_KIND = "Conclusion"

TABLE_KIND = "Table"
"""The one artifact kind an authored module may define the shape of (ADR-030)."""


def model_for(kind: str) -> type[ArtifactData]:
    try:
        return ARTIFACT_MODELS[kind]
    except KeyError as exc:  # pragma: no cover - loader guards this
        raise KeyError(f"unknown artifact kind {kind!r}") from exc


class Artifact(BaseModel):
    """Envelope. `data` stays a dict so the engine never imports a concrete type."""

    kind: str
    schema_version: int = 1
    module: ModuleId
    stage_id: StageId
    title: str = ""
    notes: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    def typed(self) -> ArtifactData:
        return model_for(self.kind).model_validate(self.data)

    @classmethod
    def of(
        cls,
        *,
        module: ModuleId,
        stage_id: StageId,
        kind: str,
        data: ArtifactData,
        title: str = "",
    ) -> "Artifact":
        return cls(
            kind=kind,
            module=module,
            stage_id=stage_id,
            title=title,
            notes=data.notes,
            data=data.model_dump(mode="json"),
        )
