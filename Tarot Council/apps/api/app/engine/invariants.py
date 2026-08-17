"""Invariant validators (ADR-012).

Instructions are advisory; validators are not. Each entry returns a list of
complaints — empty means valid. Complaints are shown verbatim to the model in the
repair pass, so they are written as actionable imperatives.

Two passes run before these:
  1. NORMALIZERS  — server-side computation the model is not trusted with
                    (ratios, power-gap tagging, do_nothing insertion)
  2. schema validation via the Pydantic model

`engine/` never imports a concrete artifact class for dispatch; it looks types up
in `ARTIFACT_MODELS`. The validators below do reference concrete types, which is
the one place that is unavoidable and correct — they encode type-specific rules.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..schemas.artifacts import (
    ActorList,
    AffectedParties,
    Artifact,
    ArtifactData,
    AsymmetryTable,
    BaseRateTable,
    Conclusion,
    ConstraintAnalysis,
    ConversationScripts,
    DecisionFrame,
    EffortReturnRanking,
    EvidenceGaps,
    EvidenceLedger,
    FailureModeTable,
    HarmLedger,
    HiddenDynamics,
    InactionHarm,
    IncentiveTable,
    LeverageInventory,
    OptionSet,
    OutcomeDefinition,
    PersonList,
    PersonProfileSet,
    ProbabilityTree,
    RankedOptions,
    ReactionForecast,
    RegretMatrix,
    SelfRead,
    SequencePlan,
    SimplestPath,
    SituationRead,
    StakeholderGraph,
    Table,
    TableRow,
    TreeNode,
    UnexpectedMove,
    ValueAudit,
    WasteAudit,
)
from ..schemas.common import DO_NOTHING_ID
from ..schemas.council import DecisionContext
from ..schemas.program import Coverage, Stage

PROBABILITY_TOLERANCE = 0.02
POWER_GAP_THRESHOLD = 0.4
MIN_LEAF_PROBABILITY = 0.01
NOTES_MAX_CHARS = 400

STANCE_PATTERNS = re.compile(
    r"\b(you should|i recommend|my recommendation|my advice|the best option is|"
    r"i would advise|you ought to|the right move is|i suggest you)\b",
    re.IGNORECASE,
)

# A stance must start with a verb. Checking that properly needs a POS tagger; this
# blocklist of non-verb openers catches the failure that actually occurs — a stance
# written as a description rather than an instruction.
NON_VERB_OPENERS = {
    "i", "we", "you", "he", "she", "they", "it", "the", "a", "an", "this",
    "that", "there", "maybe", "perhaps", "probably", "my", "your", "his",
    "her", "their", "its", "klein", "lumian", "alger", "audrey", "fors",
    "leonard",
}

REQUIRED_OPTION_TAGS = {"obvious", "inverse", "free", "reckless", "reframes"}
MIN_GENERATED_OPTIONS = 7


@dataclass(slots=True)
class InvariantContext:
    """Everything a validator may consult beyond the artifact itself."""

    context: DecisionContext
    stage: Stage
    module: str
    prior: dict[str, Artifact] = field(default_factory=dict)
    """stage_id -> artifact, for this module's own earlier stages."""
    citable: set[str] = field(default_factory=set)
    """`module/stage_id/kind#row_id` strings this module may cite."""

    def prior_typed(self, kind: str) -> ArtifactData | None:
        for artifact in self.prior.values():
            if artifact.kind == kind:
                return artifact.typed()
        return None


Validator = Callable[[Any, InvariantContext], list[str]]


# ══════════════════════════════════════════════════════════════ normalizers ══
# Computed server-side, never trusted from the model.


def _norm_decision_frame(data: dict[str, Any]) -> dict[str, Any]:
    options = data.get("options") or []
    if not any(str(o.get("id", "")).lower() == DO_NOTHING_ID for o in options):
        options.append(
            {
                "id": DO_NOTHING_ID,
                "label": "Do nothing / continue as is",
                "description": "Inserted automatically: an option set without the "
                "status quo is not a decision.",
            }
        )
    data["options"] = options
    return data


def _norm_ratio(data: dict[str, Any], *, numerator: str, denominator: str) -> dict[str, Any]:
    for row in data.get("rows") or []:
        try:
            den = float(row.get(denominator) or 0)
            num = float(row.get(numerator) or 0)
        except (TypeError, ValueError):
            continue
        row["ratio"] = round(num / den, 3) if den else 0.0
    return data


def _norm_graph(data: dict[str, Any]) -> dict[str, Any]:
    for node in data.get("nodes") or []:
        try:
            gap = abs(float(node.get("formal_authority", 0.5)) - float(node.get("real_influence", 0.5)))
        except (TypeError, ValueError):
            gap = 0.0
        node["power_gap"] = gap >= POWER_GAP_THRESHOLD
    return data


NORMALIZERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "DecisionFrame": _norm_decision_frame,
    "AsymmetryTable": lambda d: _norm_ratio(d, numerator="upside_value", denominator="downside_cost"),
    "EffortReturnRanking": lambda d: _norm_ratio(d, numerator="expected_return", denominator="effort"),
    "StakeholderGraph": _norm_graph,
}


# ══════════════════════════════════════════════════════════════════ helpers ══


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings(v)]
    return []


def _blank(*values: str) -> bool:
    return any(not (v or "").strip() for v in values)


def _known_entities(ctx: InvariantContext) -> set[str]:
    return {e for e in ctx.context.named_entities() if e}


def _entity_known(label: str, known: set[str]) -> bool:
    low = label.strip().lower()
    if not low or low in {"me", "myself", "i"}:
        return True
    return any(low in k or k in low for k in known)


# ═══════════════════════════════════════════════════════════════ universals ══


def universal(data: ArtifactData, ctx: InvariantContext) -> list[str]:
    problems: list[str] = []
    dumped = data.model_dump(mode="json")

    if not ctx.stage.terminal:
        for text in _strings(dumped):
            match = STANCE_PATTERNS.search(text)
            if match:
                problems.append(
                    f"stage '{ctx.stage.id}' is not the terminal stage and may not "
                    f"contain a recommendation; found {match.group(0)!r}. Describe "
                    "what you found, not what should be done."
                )
                break

    if ctx.stage.min_items:
        for name, value in dumped.items():
            if isinstance(value, list):
                if len(value) < ctx.stage.min_items:
                    problems.append(
                        f"'{name}' has {len(value)} entries; this stage requires at "
                        f"least {ctx.stage.min_items}."
                    )
                break

    for name, value in dumped.items():
        if not isinstance(value, list):
            continue
        ids = [row.get("id") for row in value if isinstance(row, dict) and "id" in row]
        if len(ids) != len(set(ids)):
            problems.append(f"'{name}' has duplicate row ids; ids must be unique.")

    if data.notes and len(data.notes) > NOTES_MAX_CHARS:
        problems.append(
            f"'notes' is {len(data.notes)} characters; keep it under {NOTES_MAX_CHARS} "
            "(about two sentences). It is a caveat field, not a place for conclusions."
        )
    return problems


# ═══════════════════════════════════════════════════════════════════ analyst ══


def _v_decision_frame(d: DecisionFrame, ctx: InvariantContext) -> list[str]:
    problems = []
    if len(d.options) < 2:
        problems.append("Give at least two options; one of them must be the status quo.")
    if _blank(d.the_actual_choice):
        problems.append("'the_actual_choice' must state the real choice in one sentence.")
    return problems


def _v_evidence_ledger(d: EvidenceLedger, ctx: InvariantContext) -> list[str]:
    problems = []
    if not any(r.load_bearing for r in d.rows):
        problems.append(
            "No row is marked load_bearing. Mark at least one: which item, if false, "
            "changes the decision?"
        )
    for r in d.rows:
        if r.status == "given" and _blank(r.source):
            problems.append(f"row {r.id}: status 'given' requires a non-empty source.")
        if r.status in ("assumed", "speculative") and r.confidence > 0.7:
            problems.append(
                f"row {r.id}: confidence {r.confidence} is too high for status "
                f"'{r.status}' (max 0.7). You cannot be near-certain of an assumption."
            )
    return problems


def _v_evidence_gaps(d: EvidenceGaps, ctx: InvariantContext) -> list[str]:
    if d.rows:
        if not any(r.would_change_decision for r in d.rows) and not d.notes:
            return [
                "No gap is marked would_change_decision. Either mark one, or state in "
                "'notes' that no missing information would change the answer — which "
                "is a strong claim and should be made explicitly."
            ]
        return []
    if not d.notes:
        return [
            "List the missing information, or state in 'notes' that none would change "
            "the decision."
        ]
    return []


def _v_base_rates(d: BaseRateTable, ctx: InvariantContext) -> list[str]:
    return [
        f"row {r.id}: source_quality 'guessed' requires applicability <= 0.5 "
        f"(got {r.applicability}). A guessed rate cannot be highly applicable."
        for r in d.rows
        if r.source_quality == "guessed" and r.applicability > 0.5
    ]


def _v_probability_tree(d: ProbabilityTree, ctx: InvariantContext) -> list[str]:
    problems: list[str] = []

    def walk(node: TreeNode, depth: int) -> int:
        deepest = depth
        if node.children:
            total = sum(c.probability or 0.0 for c in node.children)
            if abs(total - 1.0) > PROBABILITY_TOLERANCE:
                problems.append(
                    f"children of '{node.id}' have probabilities summing to "
                    f"{total:.3f}; sibling probabilities must sum to 1.0."
                )
            for child in node.children:
                if child.probability is None:
                    problems.append(f"node '{child.id}' is missing a probability.")
                elif child.probability < MIN_LEAF_PROBABILITY:
                    problems.append(
                        f"node '{child.id}' has probability {child.probability}; "
                        "drop branches below 0.01 rather than modelling noise."
                    )
                deepest = max(deepest, walk(child, depth + 1))
        elif node.outcome is None:
            problems.append(f"leaf '{node.id}' has no outcome. Every leaf needs one.")
        return deepest

    if walk(d.root, 0) < 2:
        problems.append("The tree is shallower than two levels; branch outcomes further.")
    return problems


def _v_failure_modes(d: FailureModeTable, ctx: InvariantContext) -> list[str]:
    problems = []
    if len(d.rows) < 3:
        problems.append(f"Give at least three failure modes (got {len(d.rows)}).")
    problems += [
        f"row {r.id}: early_warning_signal is empty. A failure you cannot see "
        "coming is a worry, not an analysis."
        for r in d.rows
        if _blank(r.early_warning_signal)
    ]
    return problems


# ═════════════════════════════════════════════════════════════════ tactician ══


def _v_situation_read(d: SituationRead, ctx: InvariantContext) -> list[str]:
    if not d.information_asymmetries and not d.notes:
        return [
            "List at least one information asymmetry, or state in 'notes' that "
            "information is symmetric."
        ]
    return []


def _v_option_set(d: OptionSet, ctx: InvariantContext) -> list[str]:
    problems = []
    if len(d.options) < MIN_GENERATED_OPTIONS:
        problems.append(
            f"Only {len(d.options)} options; generate at least {MIN_GENERATED_OPTIONS}. "
            "Widening the option set is the point of this stage."
        )
    present = {t for o in d.options for t in o.tags}
    missing = REQUIRED_OPTION_TAGS - present
    if missing:
        problems.append(
            "The option set is missing required kinds: "
            + ", ".join(sorted(missing))
            + ". Each must be carried by at least one option."
        )
    labels = [o.label.strip().lower() for o in d.options]
    if len(labels) != len(set(labels)):
        problems.append("Two options have the same label; they must be genuinely distinct.")
    return problems


def _v_asymmetry(d: AsymmetryTable, ctx: InvariantContext) -> list[str]:
    prior = ctx.prior_typed("OptionSet")
    problems = []
    if isinstance(prior, OptionSet):
        expected = {o.id for o in prior.options}
        seen = [r.option_id for r in d.rows]
        missing = expected - set(seen)
        if missing:
            problems.append(
                "Missing rows for options: " + ", ".join(sorted(missing)) + ". Price every option."
            )
        unknown = set(seen) - expected
        if unknown:
            problems.append(
                "Rows reference options that do not exist: " + ", ".join(sorted(unknown))
            )
        if len(seen) != len(set(seen)):
            problems.append("An option is priced more than once.")
    return problems


def _v_ranked(d: RankedOptions, ctx: InvariantContext) -> list[str]:
    problems = []
    ranks = sorted(r.rank for r in d.ranking)
    if ranks != list(range(1, len(ranks) + 1)):
        problems.append(f"Ranks must be 1..{len(ranks)} with no gaps or ties; got {ranks}.")
    prior = ctx.prior_typed("OptionSet")
    if isinstance(prior, OptionSet):
        accounted = {r.option_id for r in d.ranking} | {x.option_id for x in d.dropped}
        missing = {o.id for o in prior.options} - accounted
        if missing:
            problems.append(
                "These options vanished without being ranked or dropped: "
                + ", ".join(sorted(missing))
            )
    return problems


def _v_unexpected(d: UnexpectedMove, ctx: InvariantContext) -> list[str]:
    e = d.ethics_check
    breached = [
        name
        for name, value in (
            ("uses_deception", e.uses_deception),
            ("manufactures_urgency", e.manufactures_urgency),
            ("exploits_crisis", e.exploits_crisis),
        )
        if value
    ]
    if breached:
        return [
            "This move crosses the influence boundary ("
            + ", ".join(breached)
            + "). Permitted: framing, timing, selective emphasis of true things, "
            "creating optionality, silence. Forbidden: deception, fabricated "
            "leverage, manufactured deadlines, exploiting a crisis. Propose a "
            "different move that stays inside the boundary."
        ]
    return []


def _v_reactions(d: ReactionForecast, ctx: InvariantContext) -> list[str]:
    return [
        f"row for '{r.actor}': my_counter is empty. Forecast must reach depth two — "
        "their response, then your reply."
        for r in d.rows
        if _blank(r.my_counter)
    ]


# ════════════════════════════════════════════════════════════════ strategist ══


def _v_actor_list(d: ActorList, ctx: InvariantContext) -> list[str]:
    problems = []
    users = [a for a in d.actors if a.is_user or a.id == "me"]
    if len(users) != 1:
        problems.append("Exactly one actor must be the user, with id 'me' and is_user true.")
    known = _known_entities(ctx)
    for a in d.actors:
        if a.is_user or a.id == "me" or a.inferred:
            continue
        if not _entity_known(a.label, known):
            problems.append(
                f"actor '{a.label}' is not named anywhere in the input. Use a role "
                "label (e.g. 'my manager') and set inferred true, or drop them. Do "
                "not invent named individuals."
            )
    return problems


def _v_graph(d: StakeholderGraph, ctx: InvariantContext) -> list[str]:
    problems = []
    ids = {n.id for n in d.nodes}
    if "me" not in ids:
        problems.append("The graph must contain a node with id 'me'.")
    for e in d.edges:
        if e.src not in ids or e.dst not in ids:
            problems.append(f"edge {e.src}->{e.dst} references a node that does not exist.")
    if not any(e.src == "me" or e.dst == "me" for e in d.edges):
        problems.append("No edge touches 'me'. Connect the user to the structure.")

    # Connectivity: an isolated actor is either irrelevant or a missed edge.
    if len(d.nodes) > 1:
        adjacency: dict[str, set[str]] = {n.id: set() for n in d.nodes}
        for e in d.edges:
            if e.src in adjacency and e.dst in adjacency:
                adjacency[e.src].add(e.dst)
                adjacency[e.dst].add(e.src)
        start = "me" if "me" in adjacency else next(iter(adjacency))
        seen = {start}
        queue = [start]
        while queue:
            for nxt in adjacency[queue.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        isolated = sorted(ids - seen)
        if isolated:
            problems.append(
                "These actors have no path to the rest of the graph: "
                + ", ".join(isolated)
                + ". Either add the missing relationship or remove them as irrelevant."
            )
    return problems


def _v_incentives(d: IncentiveTable, ctx: InvariantContext) -> list[str]:
    problems = []
    prior = ctx.prior_typed("StakeholderGraph")
    if isinstance(prior, StakeholderGraph):
        expected = {n.id for n in prior.nodes} - {"me"}
        missing = expected - {r.actor_id for r in d.rows}
        if missing:
            problems.append("No incentive row for: " + ", ".join(sorted(missing)))
    problems += [
        f"row for '{r.actor_id}': 'will_never_say' is empty — that field is where "
        "the useful content lives."
        for r in d.rows
        if _blank(r.will_never_say)
    ]
    return problems


def _v_leverage(d: LeverageInventory, ctx: InvariantContext) -> list[str]:
    problems = []
    if _blank(d.my_batna.description):
        problems.append("my_batna must describe what happens if no agreement is reached.")
    problems += [
        f"leverage '{item.id}' has no expiry. An advantage that never expires is "
        "almost always an illusion — say when it lapses."
        for item in d.i_control
        if _blank(item.expiry)
    ]
    return problems


def _v_hidden(d: HiddenDynamics, ctx: InvariantContext) -> list[str]:
    if d.confidence > 0.6:
        return [
            f"confidence {d.confidence} is too high for inferred politics (max 0.6). "
            "This stage reasons about hidden structure from limited evidence."
        ]
    return []


def _v_sequence(d: SequencePlan, ctx: InvariantContext) -> list[str]:
    problems = []
    orders = sorted(s.order for s in d.steps)
    if orders != list(range(1, len(orders) + 1)):
        problems.append(f"Step order must be 1..{len(orders)} with no gaps; got {orders}.")
    problems += [
        f"step {s.order}: 'if_it_fails' is empty. Every step needs a fallback."
        for s in d.steps
        if _blank(s.if_it_fails)
    ]
    return problems


# ══════════════════════════════════════════════════════════════ psychologist ══


def _v_person_list(d: PersonList, ctx: InvariantContext) -> list[str]:
    problems = []
    if not any(p.is_user or p.id == "me" for p in d.people):
        problems.append("The cast must include the user, with id 'me'.")
    known = _known_entities(ctx)
    for p in d.people:
        if p.is_user or p.id == "me" or p.inferred:
            continue
        if not _entity_known(p.label, known):
            problems.append(
                f"'{p.label}' is not named in the input. Use a role label and set "
                "inferred true rather than inventing a name."
            )
    return problems


def _v_profiles(d: PersonProfileSet, ctx: InvariantContext) -> list[str]:
    problems = []
    prior = ctx.prior_typed("PersonList")
    inferred_ids: set[str] = set()
    if isinstance(prior, PersonList):
        expected = {p.id for p in prior.people}
        inferred_ids = {p.id for p in prior.people if p.inferred}
        got = {p.person_id for p in d.profiles}
        missing = expected - got
        if missing:
            problems.append(
                "Missing a profile for: "
                + ", ".join(sorted(missing))
                + ". Every person named in the cast gets all nine dimensions — no "
                "partial profiles, no skipping the awkward one."
            )
        unknown = got - expected
        if unknown:
            problems.append("Profiles for people not in the cast: " + ", ".join(sorted(unknown)))

    for p in d.profiles:
        empties = [
            name
            for name in (
                "driving_emotion",
                "fear",
                "unmet_need",
                "motivation",
                "reaction_if_accepted",
                "reaction_if_rejected",
                "what_they_wont_say",
            )
            if _blank(getattr(p, name))
        ]
        if empties:
            problems.append(
                f"profile '{p.person_id}' has empty fields: {', '.join(empties)}. "
                "All nine dimensions are required."
            )
        # Proxy for the doc's "described in under ~20 words": a person the user
        # never named cannot be read to high confidence.
        if p.person_id in inferred_ids and p.confidence > 0.5:
            problems.append(
                f"profile '{p.person_id}' is an inferred person; confidence must be "
                f"<= 0.5 (got {p.confidence})."
            )
    return problems


def _v_self_read(d: SelfRead, ctx: InvariantContext) -> list[str]:
    haystack = ctx.context.question.lower()
    quoted = [
        q for q in d.evidence_from_phrasing if len(q.strip()) >= 8 and q.strip().lower() in haystack
    ]
    if not quoted:
        return [
            "'evidence_from_phrasing' must contain at least one verbatim quote (8+ "
            "characters) copied exactly from the user's own words. A read on someone "
            "you cannot see must be anchored in what they actually wrote."
        ]
    return []


def _v_scripts(d: ConversationScripts, ctx: InvariantContext) -> list[str]:
    problems = []
    described = re.compile(
        r"^\s*(explain|tell them|describe|discuss|mention|convey|communicate|let them know)\b",
        re.IGNORECASE,
    )
    for s in d.scripts:
        if _blank(s.opening):
            problems.append(f"script for '{s.person_id}': 'opening' is empty.")
        elif described.match(s.opening):
            problems.append(
                f"script for '{s.person_id}': 'opening' describes an approach rather "
                "than giving the words. Write what the user actually says, out loud."
            )
    return problems


# ═════════════════════════════════════════════════════════════════ optimizer ══


def _v_outcome(d: OutcomeDefinition, ctx: InvariantContext) -> list[str]:
    problems = []
    if len(d.outcome.split()) > 30:
        problems.append(f"'outcome' is {len(d.outcome.split())} words; keep it under 30.")
    if _blank(d.metric, d.how_we_would_know):
        problems.append("'metric' and 'how_we_would_know' must both be filled in.")
    return problems


def _v_waste(d: WasteAudit, ctx: InvariantContext) -> list[str]:
    if d.rows and all(r.verdict == "keep" for r in d.rows) and not d.notes:
        return [
            "Every row is 'keep'. If nothing is wasteful, say so explicitly in "
            "'notes' — that is a strong claim and should be stated as one."
        ]
    return []


def _v_constraint(d: ConstraintAnalysis, ctx: InvariantContext) -> list[str]:
    problems = []
    text = d.binding_constraint.strip()
    if not text:
        problems.append("Name the single binding constraint.")
    elif re.search(r"\b(and|as well as|plus)\b", text, re.IGNORECASE) or ";" in text:
        problems.append(
            f"'binding_constraint' names more than one thing ({text!r}). Exactly one "
            "constraint is binding; put the others in 'non_constraints'."
        )
    if _blank(d.if_relieved):
        problems.append("'if_relieved' must say what becomes possible.")
    return problems


def _v_simplest(d: SimplestPath, ctx: InvariantContext) -> list[str]:
    problems = []
    if _blank(d.do_nothing_baseline.what_happens):
        problems.append(
            "'do_nothing_baseline' must honestly describe what happens with no "
            "action. It is the option everyone else forgets to price."
        )
    if _blank(d.simplest_sufficient, d.one_tenth_time_version):
        problems.append("Both 'simplest_sufficient' and 'one_tenth_time_version' are required.")
    return problems


def _v_effort_return(d: EffortReturnRanking, ctx: InvariantContext) -> list[str]:
    if not any(r.option_id == DO_NOTHING_ID for r in d.rows):
        return [f"Include a '{DO_NOTHING_ID}' row. Doing nothing is an option and must be priced."]
    return []


# ══════════════════════════════════════════════════════════════════ ethicist ══


def _v_parties(d: AffectedParties, ctx: InvariantContext) -> list[str]:
    problems = []
    if not any(p.future_self for p in d.parties):
        problems.append("Include the user's future self as an affected party.")
    if not any(not p.in_the_room for p in d.parties) and not d.notes:
        problems.append(
            "Every party is in the room. Name someone affected who is absent, or "
            "justify in 'notes' that nobody outside the room is affected."
        )
    return problems


def _v_values(d: ValueAudit, ctx: InvariantContext) -> list[str]:
    problems = []
    stated = [r for r in d.rows if r.source == "stated_by_user"]
    haystack = ctx.context.question.lower()
    if not stated and not d.notes:
        problems.append(
            "No value is sourced to the user. Quote one from their own words, or "
            "state in 'notes' that they expressed none."
        )
    for r in stated:
        if _blank(r.quote or ""):
            problems.append(f"row {r.id}: source 'stated_by_user' requires a verbatim quote.")
        elif (r.quote or "").strip().lower() not in haystack:
            problems.append(
                f"row {r.id}: quote {r.quote!r} does not appear in the user's words. "
                "Quote exactly or change the source to 'inferred_from_user'."
            )
    conventional = sum(1 for r in d.rows if r.source == "conventional")
    if d.rows and conventional > len(d.rows) / 2:
        problems.append(
            "More than half the values are 'conventional'. Reason from this user's "
            "values, not from a framework they did not choose."
        )
    return problems


def _v_harm(d: HarmLedger, ctx: InvariantContext) -> list[str]:
    problems = []
    if not any(r.option_id == DO_NOTHING_ID for r in d.rows):
        problems.append(f"Score the '{DO_NOTHING_ID}' option too — inaction has costs.")
    problems += [
        f"row for '{r.option_id}': magnitude {r.magnitude} but 'who_pays' is empty. "
        "Name who absorbs it."
        for r in d.rows
        if r.magnitude > 0 and not r.who_pays
    ]
    return problems


def _v_regret(d: RegretMatrix, ctx: InvariantContext) -> list[str]:
    if not d.rows:
        return ["Score regret for every option at 1, 5 and 10 years."]
    return []


def _v_inaction(d: InactionHarm, ctx: InvariantContext) -> list[str]:
    empties = [
        name
        for name in ("harm_of_delay", "harm_of_status_quo", "decay")
        if _blank(getattr(d, name))
    ]
    if empties:
        return [
            f"These fields are required and empty: {', '.join(empties)}. You must "
            "price inaction before concluding."
        ]
    return []


# ══════════════════════════════════════════════════════════════════ terminal ══


def _v_conclusion(d: Conclusion, ctx: InvariantContext) -> list[str]:
    problems = []
    if _blank(d.stance):
        problems.append("'stance' is empty.")
    else:
        first = re.split(r"[^A-Za-z']+", d.stance.strip(), maxsplit=1)[0].lower()
        if first in NON_VERB_OPENERS:
            problems.append(
                f"'stance' starts with {first!r}; it must be an instruction beginning "
                "with a verb (e.g. 'Stay for three months and…')."
            )
    if _blank(d.first_action):
        problems.append("'first_action' must name something doable within 48 hours.")
    if _blank(d.confidence.falsifier):
        problems.append(
            "'confidence.falsifier' is required: the single observation that would "
            "flip this stance."
        )

    if ctx.citable:
        refs = {
            f"{c.module}/{c.stage_id}/{c.kind}#{c.row_id}" if c.row_id else f"{c.module}/{c.stage_id}/{c.kind}"
            for c in d.key_claims
        }
        if not refs:
            problems.append(
                "'key_claims' is empty. Cite the artifact rows this stance rests on, "
                "using the identifiers listed under CITABLE ROWS."
            )
        else:
            unknown = sorted(refs - ctx.citable)
            if unknown:
                problems.append(
                    "These key_claims do not match any citable row: "
                    + ", ".join(unknown[:5])
                    + ". Use the identifiers exactly as listed."
                )

    # The mechanical form of "never hallucinate confidence": high confidence is
    # arithmetically unavailable over admitted assumptions.
    if d.confidence.score >= 0.8:
        ledger = ctx.prior_typed("EvidenceLedger")
        if isinstance(ledger, EvidenceLedger):
            cited = {c.row_id for c in d.key_claims if c.row_id}
            soft = [
                r.id
                for r in ledger.rows
                if r.id in cited and r.status in ("assumed", "speculative")
            ]
            if soft:
                problems.append(
                    f"confidence {d.confidence.score} requires no assumed or "
                    f"speculative claims, but you cited {', '.join(soft)}. Either "
                    "lower confidence below 0.8 or rest the stance on firmer rows."
                )
    if d.ethical_veto and _blank(d.veto_grounds or ""):
        problems.append("'ethical_veto' is set but 'veto_grounds' is empty.")
    return problems


# ═════════════════════════════════════════════════════════════════ registry ══

def _cell(row: TableRow, column: str) -> str:
    value = row.cells.get(column)
    return "" if value is None else str(value).strip()


def _number(row: TableRow, column: str) -> float | None:
    try:
        return float(row.cells.get(column))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _v_table(d: Table, ctx: InvariantContext) -> list[str]:
    """Enforce the stage's declared `TableSpec` (ADR-030).

    This is the interpreter that makes "no code" mean something. Every branch below is a
    declarative restatement of a rule the built-in six already assert in hand-written
    Python, so an authored module is held to the same *kind* of standard even though it
    ships no Python of its own.

    The messages are written to be repaired: the executor feeds them straight back to the
    model, so "row 'r2' has an empty 'mechanism'" is worth several times "invalid table".
    """
    spec = ctx.stage.table
    if spec is None:
        # Refusing rather than passing. A table with no declared constraints is a freeform
        # blob the model fills however it likes — the persona-with-a-prompt failure that
        # loader rule 4 exists to prevent, and the loader normally catches it first. Reaching
        # here means something bypassed the loader.
        return [
            f"stage '{ctx.stage.id}' produces a Table but declares no table spec; "
            "an artifact with no constraints cannot be validated"
        ]

    problems: list[str] = []
    rows = list(d.rows)

    if len(rows) < spec.min_rows:
        problems.append(
            f"{len(rows)} row(s); this stage requires at least {spec.min_rows}."
        )

    ids = [r.id.strip() for r in rows]
    if len(ids) != len(set(ids)):
        problems.append("Two rows share an id; every row needs a distinct one to be citable.")
    if any(not i for i in ids):
        problems.append("A row has an empty id.")

    declared = set(spec.columns)
    for row in rows:
        unknown = set(row.cells) - declared
        if declared and unknown:
            problems.append(
                f"row '{row.id}' has undeclared column(s) {', '.join(sorted(unknown))}; "
                f"this table's columns are: {', '.join(spec.columns)}."
            )
        empties = [c for c in spec.required if not _cell(row, c)]
        if empties:
            problems.append(
                f"row '{row.id}' has empty required column(s): {', '.join(empties)}. "
                "Every row must fill all of them."
            )

    for column in spec.distinct:
        values = [_cell(row, column).lower() for row in rows if _cell(row, column)]
        if len(values) != len(set(values)):
            problems.append(
                f"Two rows share a '{column}'; values in that column must be genuinely "
                "distinct."
            )

    present = {tag for row in rows for tag in row.tags}
    missing_tags = [t for t in spec.required_tags if t not in present]
    if missing_tags:
        problems.append(
            "The table is missing required kinds: "
            + ", ".join(missing_tags)
            + ". Each must be carried by at least one row."
        )

    for rule in spec.ranges:
        for row in rows:
            if not _cell(row, rule.column):
                continue
            value = _number(row, rule.column)
            if value is None:
                problems.append(
                    f"row '{row.id}' has a non-numeric '{rule.column}'; it must be a number."
                )
                continue
            if rule.minimum is not None and value < rule.minimum:
                problems.append(
                    f"row '{row.id}' has {rule.column}={value}, below the minimum "
                    f"{rule.minimum}."
                )
            if rule.maximum is not None and value > rule.maximum:
                problems.append(
                    f"row '{row.id}' has {rule.column}={value}, above the maximum "
                    f"{rule.maximum}."
                )

    if spec.sums_to is not None:
        rule = spec.sums_to
        # Name the offending cell rather than reporting the total. `or 0.0` used to swallow a
        # non-numeric value, so "about half" produced "sums to 0.500" and sent the repair
        # pass to fix arithmetic instead of the cell that is not a number.
        unparseable = [r.id for r in rows if _number(r, rule.column) is None]
        if unparseable:
            problems.append(
                f"row(s) {', '.join(unparseable)} have a non-numeric '{rule.column}'; "
                f"it must be a number so the column can be summed."
            )
        else:
            total = sum(_number(row, rule.column) or 0.0 for row in rows)
            if abs(total - rule.total) > rule.tolerance:
                problems.append(
                    f"'{rule.column}' sums to {total:.3f}; it must sum to {rule.total} "
                    f"(±{rule.tolerance})."
                )

    if spec.covers is not None:
        problems += _check_coverage(d, ctx, spec.covers)

    return problems


def _check_coverage(d: Table, ctx: InvariantContext, covers: "Coverage") -> list[str]:
    """Every value in an earlier stage's column must appear in this table.

    Checked across a stage boundary, which is what makes a multi-stage authored module more
    than a sequence of unrelated prompts. Generalises the psychologist's rule that every
    person named in the cast gets a full profile.
    """
    prior = ctx.prior.get(covers.stage)
    if prior is None:
        # Not the model's fault, and not silently ignorable either: the loader checks that
        # `covers.stage` is an earlier stage, so an absent artifact means that stage
        # abstained. Skipping the check is right — there is nothing to cover.
        return []

    expected: set[str] = set()
    for row in (prior.data.get("rows") or []):
        if isinstance(row, dict):
            cells = row.get("cells") or {}
            value = cells.get(covers.column) if isinstance(cells, dict) else None
            if value is None:
                value = row.get(covers.column) or row.get("id")
            if value is not None and str(value).strip():
                expected.add(str(value).strip())

    if not expected:
        return []

    into = covers.into or covers.column
    got = {_cell(row, into) for row in d.rows if _cell(row, into)}
    missing = expected - got
    problems: list[str] = []
    if missing:
        problems.append(
            f"Missing a row for: {', '.join(sorted(missing))}. Every '{covers.column}' from "
            f"stage '{covers.stage}' needs one here — no partial coverage, no skipping the "
            "awkward one."
        )
    invented = got - expected
    if invented:
        problems.append(
            f"Rows for values not in stage '{covers.stage}': {', '.join(sorted(invented))}."
        )
    return problems


INVARIANTS: dict[str, Validator] = {
    "DecisionFrame": _v_decision_frame,
    "EvidenceLedger": _v_evidence_ledger,
    "EvidenceGaps": _v_evidence_gaps,
    "BaseRateTable": _v_base_rates,
    "ProbabilityTree": _v_probability_tree,
    "FailureModeTable": _v_failure_modes,
    "SituationRead": _v_situation_read,
    "OptionSet": _v_option_set,
    "AsymmetryTable": _v_asymmetry,
    "RankedOptions": _v_ranked,
    "UnexpectedMove": _v_unexpected,
    "ReactionForecast": _v_reactions,
    "ActorList": _v_actor_list,
    "StakeholderGraph": _v_graph,
    "IncentiveTable": _v_incentives,
    "LeverageInventory": _v_leverage,
    "HiddenDynamics": _v_hidden,
    "SequencePlan": _v_sequence,
    "PersonList": _v_person_list,
    "PersonProfileSet": _v_profiles,
    "SelfRead": _v_self_read,
    "ConversationScripts": _v_scripts,
    "OutcomeDefinition": _v_outcome,
    "WasteAudit": _v_waste,
    "ConstraintAnalysis": _v_constraint,
    "SimplestPath": _v_simplest,
    "EffortReturnRanking": _v_effort_return,
    "AffectedParties": _v_parties,
    "ValueAudit": _v_values,
    "HarmLedger": _v_harm,
    "RegretMatrix": _v_regret,
    "InactionHarm": _v_inaction,
    "Table": _v_table,
    "Conclusion": _v_conclusion,
}

# Types with no type-specific rules beyond the universals. Listed explicitly so a
# missing validator is a loader error rather than a silent gap.
#
# `Table` is deliberately NOT here: it has a validator, and that validator refuses a table
# whose stage declared no spec. An authored artifact with no declared constraints is exactly
# what rule 4 exists to prevent.
NO_EXTRA_INVARIANTS: frozenset[str] = frozenset(
    {"RelationshipEdges", "EmotionalCostTable", "SystemDesign", "IntegrityCheck"}
)


def normalize(kind: str, data: dict[str, Any]) -> dict[str, Any]:
    fn = NORMALIZERS.get(kind)
    return fn(data) if fn else data


def check(kind: str, data: ArtifactData, ctx: InvariantContext) -> list[str]:
    problems = universal(data, ctx)
    validator = INVARIANTS.get(kind)
    if validator is not None:
        problems += validator(data, ctx)
    return problems


def has_coverage(kind: str) -> bool:
    return kind in INVARIANTS or kind in NO_EXTRA_INVARIANTS
