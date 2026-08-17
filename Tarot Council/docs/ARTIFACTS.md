# Artifact registry

An artifact is a **named type with machine-checkable invariants** — not "the
model's structured output". Instructions are advisory; validators are not. This
file is the authority on what may exist in a reasoning trace.

Every entry has:

- a Pydantic model in `apps/api/app/schemas/artifacts/`
- an invariant validator in `apps/api/app/engine/invariants/`
- a renderer in `apps/web/components/artifacts/`

Adding an artifact type means adding all three. The loader refuses a program that
produces a type missing any of them.

---

## Common envelope

```python
class Artifact(BaseModel):
    kind: ArtifactKind          # discriminator
    schema_version: int = 1
    module: ModuleId
    stage_id: StageId
    title: str                  # human label for the trace node
    notes: str | None = None    # ≤ 2 sentences; not a place for conclusions
    data: <kind-specific>
```

`notes` is length-capped on purpose. Without a cap it becomes the field where
models hide the answer they were told not to give yet.

### Universal invariants

Applied to every artifact regardless of kind:

- **No premature stance.** `data` and `notes` are scanned for
  recommendation patterns (`you should`, `I recommend`, `the best option is`,
  `my advice`) on any artifact whose stage is not `terminal`. A hit is a
  validation failure and triggers the repair pass.
- **No empty collections** where the stage's `min_items` says otherwise.
- **No fabricated proper nouns.** Enforced on the artifacts that enumerate
  people — `ActorList`, `PersonList`, `AffectedParties`. Any entry whose label
  does not match something in the `DecisionContext` must carry `inferred: true`;
  a module needing an actor the user never mentioned must use a role label
  (`"the hiring manager"`), never an invented name. A general scan for invented
  proper nouns across all prose fields is deliberately *not* attempted — it
  false-positives on ordinary capitalised words, and a validator that cries wolf
  is worse than none.
- **Row ids are stable and unique** within the artifact (`e1`, `a3`, `n2`), because
  critiques target them and the trace draws edges to them. Not every artifact
  keys rows on `id` — a sequence step is identified by `order`, a harm row by
  `option_id`, a profile by `person_id` — and all of those forms are citable
  (`engine/executor.py:ROW_KEYS`). Recognising only `id` showed up in the first
  live run as a wasted repair call against a row that was in fact real.

---

## Analyst artifacts

### `DecisionFrame`
```python
options: list[Option]        # id, label, description
the_actual_choice: str       # one sentence — often not the question asked
time_box: str | None         # when this must be decided, and why
reversibility: Literal["reversible", "costly", "one_way"]
success_criteria: list[str]  # how we would know, concretely
```
**Invariants** · ≥2 options, and one of them must be the status quo (`do_nothing`
is auto-inserted if absent — an option set without it is not a decision).
`the_actual_choice` must differ textually from the raw question or state
explicitly that it does not.

### `EvidenceLedger`
```python
rows: list[EvidenceRow]
  id, statement
  status: Literal["given","inferred","assumed","speculative","unknown"]
  source: str              # for `given`: where from. for `assumed`: whose assumption.
  load_bearing: bool       # does the decision change if this is false?
  confidence: float        # 0..1
```
**Invariants** · ≥1 row with `load_bearing: true`. Every `given` row has a
non-empty `source`. Every `assumed`/`speculative` row has `confidence ≤ 0.7` —
you may not be certain of something you have labelled an assumption. No row text
contains a recommendation verb.

### `EvidenceGaps`
```python
rows: list[Gap]
  id, question
  why_it_matters: str
  would_change_decision: bool
  cost_to_resolve: Literal["free","cheap","expensive","impossible"]
  how_to_resolve: str
```
**Invariants** · ≥1 row with `would_change_decision: true` **or** an explicit
`notes` statement that no missing information would change the answer — which is
a strong claim and is therefore a prime critique target.

### `BaseRateTable`
```python
rows: list[BaseRate]
  id, reference_class: str      # "people who quit an internship at 6 months"
  observed_rate: str            # may be qualitative if honest
  applicability: float          # 0..1 — how well the user matches the class
  source_quality: Literal["measured","reported","estimated","guessed"]
```
**Invariants** · `source_quality: guessed` rows must have `applicability ≤ 0.5`.
This is the specific anti-hallucination guard for the module most likely to
produce authoritative-sounding invented statistics.

### `ProbabilityTree`
```python
root: TreeNode
TreeNode:
  id, label
  probability: float | None      # None only at root
  condition: str | None          # what makes this branch happen
  outcome: Outcome | None        # leaves only: description, valence -1..1, magnitude
  children: list[TreeNode]
```
**Invariants** · sibling probabilities sum to `1.0 ± 0.02`; depth ≥ 2; every leaf
has an `outcome`; no leaf probability below 0.01 (noise, not analysis). **This is
the strongest validator in the system** — a model cannot fake a coherent
probability tree, and the arithmetic check catches sloppiness that reads fine in
prose.

### `FailureModeTable`
```python
rows: list[FailureMode]
  id, scenario                  # written as though it already happened
  trigger: str
  probability: float
  severity: int                 # 1..5
  early_warning_signal: str     # observable before it is too late
  mitigation: str
```
**Invariants** · ≥3 rows. Every row has a non-empty `early_warning_signal` — a
failure mode you cannot see coming is a worry, not an analysis.

---

## Tactician artifacts

### `SituationRead`
```python
game_being_played: str
who_thinks_otherwise: list[Misread]      # actor, what they think the game is
information_asymmetries: list[Asymmetry]  # holder, what they know, exploitable?
tempo: TempoRead                          # who is under time pressure, whose clock
```
**Invariants** · ≥1 asymmetry, or an explicit statement that information is
symmetric.

### `OptionSet`
```python
options: list[GeneratedOption]
  id, label, description
  tags: list[OptionTag]
OptionTag = obvious | inverse | free | reckless | reframes | conventional | hybrid
```
**Invariants** · **≥7 options**, and the set must collectively carry the tags
`obvious`, `inverse`, `free`, `reckless`, and `reframes`. This quota is the whole
mechanism of the module — without it, "generate options" returns three variations
of the obvious one. Duplicate labels rejected by fuzzy match.

### `AsymmetryTable`
```python
rows: list[AsymmetryRow]
  option_id                       # must reference OptionSet
  max_downside, realistic_upside: str
  downside_cost, upside_value: int  # 1..5, for the ratio
  ratio: float                      # computed, validated
  reversibility: Literal["reversible","costly","one_way"]
  time_to_know: str                 # how long before you learn if it worked
```
**Invariants** · every `OptionSet` option appears exactly once; `ratio` matches
`upside_value / downside_cost` within tolerance (computed server-side, not
trusted from the model).

### `RankedOptions`
```python
ranking: list[RankedRow]           # option_id, rank, rationale, score
dropped: list[DroppedRow]          # option_id, why — nothing vanishes silently
```
**Invariants** · ranks are a permutation of 1..n with no gaps; every option is
either ranked or explicitly dropped with a reason.

### `UnexpectedMove`
```python
move: str
why_available: str                # why nobody else has taken it
what_it_forces: str               # the reaction it compels
cost_if_wrong: str
ethics_check: EthicsCheck         # uses_deception, manufactures_urgency,
                                  # exploits_crisis: all must be false + rationale
```
**Invariants** · all three `ethics_check` booleans must be `false`. If any is
`true`, the artifact is rejected and regenerated with the boundary restated
(ADR-009). This is where "ethical manipulation" stops being a vibe and becomes a
gate.

### `ReactionForecast`
```python
rows: list[Reaction]
  actor, my_move, their_likely_response
  probability: float
  my_counter: str                 # move 2
  tempo_effect: str
```
**Invariants** · every row reaches depth 2 (`my_counter` non-empty). Actors must
exist in the context or be role-labelled.

---

## Strategist artifacts

### `ActorList`
```python
actors: list[Actor]               # id, label, role, is_user, inferred
```
**Invariants** · exactly one actor with `is_user: true` and `id == "me"`.

### `StakeholderGraph`
```python
nodes: list[GraphNode]
  id, label, role
  formal_authority: float         # 0..1 — what the org chart says
  real_influence: float           # 0..1 — what actually moves outcomes
  controls: list[str]             # resources, decisions, information
  fears: list[str]
  optimising_for: str             # what they actually want
  stated_position: str | None
  actual_interest: str | None
edges: list[GraphEdge]
  src, dst
  kind: reports_to | depends_on | owes | allied_with | competes_with
      | can_veto | informs | gatekeeps
  weight: float                   # 0..1 strength
  is_hidden: bool                 # not visible on the org chart
```
**Invariants** · a node with `id == "me"` exists; the graph is **connected** (an
isolated actor is either irrelevant or the edge was missed — both worth
surfacing); every edge endpoint resolves; `formal_authority`/`real_influence` in
[0,1]; ≥1 edge incident on `me`. Nodes where
`|formal_authority − real_influence| ≥ 0.4` are auto-tagged `power_gap` and
highlighted in the trace — that gap is usually where the decision is really made.

### `IncentiveTable`
```python
rows: list[Incentive]
  actor_id, rewarded_for, punished_for
  will_never_say: str
  misalignment_with_me: str
  severity: int                   # 1..5
```
**Invariants** · one row per graph node (except `me`, which is optional).

### `LeverageInventory`
```python
i_control: list[Leverage]          # what, who wants it, strength, expiry
my_batna: Batna                    # description, strength 0..1, honest_assessment
their_batna: list[Batna]           # per counterparty
```
**Invariants** · `my_batna` non-empty. Every leverage item has an `expiry` — an
unexpiring advantage is almost always an illusion.

### `HiddenDynamics`
```python
debts: list[Debt]                  # who owes whom, for what, callable?
alliances: list[Alliance]
upcoming_shifts: list[Shift]       # event, when, who gains, who loses
confidence: float                  # this stage is the most speculative
```
**Invariants** · `confidence ≤ 0.6` unless the context contains direct evidence.
Politics inferred from a paragraph of user context does not deserve high
confidence, and this validator says so numerically.

### `SequencePlan`
```python
steps: list[SequenceStep]
  order: int, actor_id, objective
  must_yield_before_next: str
  if_it_fails: str
  commit_point: bool               # after this, retreat is expensive
```
**Invariants** · `order` is 1..n contiguous; ≥1 step; every step has
`if_it_fails`.

---

## Psychologist artifacts

### `PersonList`
```python
people: list[Person]               # id, label, relationship_to_user, is_user
```
**Invariants** · includes `me`.

### `PersonProfileSet`
```python
profiles: list[PersonProfile]
  person_id
  driving_emotion: str
  fear: str
  unmet_need: str
  motivation: str
  stress_level: int                # 1..5
  reaction_if_accepted: str        # if the decision goes their way
  reaction_if_rejected: str        # if it does not
  what_they_wont_say: str
  confidence: float
```
**Invariants** · **one complete profile for every person in `PersonList`, all
nine fields non-empty.** No partial profiles, no skipping the awkward one. This
is the module's defining constraint: the same nine dimensions for every person,
every single time, so profiles are comparable across people and across decisions.
`confidence ≤ 0.5` for any person carrying `inferred: true` in the cast — i.e.
whom the user never actually named. (That flag is the tractable proxy for "the
user described them in barely a sentence": it is checkable, whereas
attributing a word count to a particular person in free text is not.)

### `SelfRead`
```python
stated_feeling: str
likely_real_feeling: str
evidence_from_phrasing: list[str]  # must quote the user's own words
what_is_being_avoided: str
question_behind_the_question: str
confidence: float
```
**Invariants** · `evidence_from_phrasing` must contain ≥1 verbatim substring of
the user's input. This is the anti-projection guard: a psychological read on
someone you cannot see must be anchored in what they actually wrote.

### `RelationshipEdges`
```python
edges: list[RelationEdge]
  a, b, dynamic
  tension: int                     # 0..5
  who_holds_emotional_leverage: str | None
```

### `ConversationScripts`
```python
scripts: list[Script]
  person_id, goal
  opening: str                     # the actual words
  likely_objection: str
  response: str
  what_not_to_say: str
```
**Invariants** · `opening` must be quotable speech, not a description of an
approach — validated by rejecting rows whose text reads as instruction
("explain that you…"). A script the user cannot say out loud has failed.

### `EmotionalCostTable`
```python
rows: list[CostRow]
  option_id, cost_to_me: int       # 1..5
  cost_to_others: list[PersonCost]
  recovery_time: str
```

---

## Optimizer artifacts

### `OutcomeDefinition`
```python
outcome: str                       # one measurable sentence
metric: str
deadline: str | None
how_we_would_know: str
```
**Invariants** · `outcome` ≤ 30 words and must contain a measurable term.

### `WasteAudit`
```python
rows: list[WasteRow]
  id, activity, cost: str          # hours/week or money
  outcome_produced: str
  verdict: Literal["keep","cut","automate","delegate","defer"]
  rationale: str
```
**Invariants** · ≥1 non-`keep` verdict, or explicit notes that nothing is
wasteful — again, a strong claim and a critique target.

### `ConstraintAnalysis`
```python
binding_constraint: str            # exactly one
evidence: list[str]
if_relieved: str                   # what becomes possible
non_constraints: list[NonConstraint]  # things that look binding but are not
```
**Invariants** · exactly one `binding_constraint`, singular, no conjunctions
(rejected if it contains " and "). Naming two constraints is refusing to do the
analysis.

### `SimplestPath`
```python
do_nothing_baseline: Baseline      # what happens with no action, honestly
simplest_sufficient: str
one_tenth_time_version: str        # if you had 10% of the time
what_gets_dropped: list[str]
```
**Invariants** · all four fields present. The `do_nothing_baseline` is mandatory
because it is the option every other module forgets to price.

### `EffortReturnRanking`
```python
rows: list[ErRow]
  option_id, effort: int           # 1..5
  expected_return: int             # 1..5
  ratio: float                     # computed
  simpler_version: str | None
```
**Invariants** · includes a `do_nothing` row; `ratio` recomputed server-side.

### `SystemDesign`
```python
rule: str                          # so this decision never needs making again
trigger: str
automation: str | None
maintenance_cost: str
```

---

## Ethicist artifacts

### `AffectedParties`
```python
parties: list[Party]
  id, label
  in_the_room: bool                # people affected but absent are the point
  can_consent: bool
  future_self: bool
```
**Invariants** · must include the user's future self and ≥1 party with
`in_the_room: false`, or explicit notes justifying that nobody outside the room
is affected.

### `ValueAudit`
```python
rows: list[ValueRow]
  id, value
  source: Literal["stated_by_user","inferred_from_user","conventional"]
  quote: str | None                # required when source is stated_by_user
  options_serving: list[str]
  options_violating: list[str]
```
**Invariants** · ≥1 row with `source: stated_by_user` **or** explicit notes that
the user stated no values. `conventional` rows are capped at half the table.
This is the guard against the module importing a moral framework the user does
not hold — it must reason from *their* values, quoted.

### `HarmLedger`
```python
rows: list[HarmRow]
  option_id, who_pays: list[str]
  magnitude: int                   # 1..5
  reversible: bool
  consented: bool
  alternative_that_avoids: str | None
```
**Invariants** · every option scored, including `do_nothing`; `who_pays`
non-empty wherever `magnitude > 0`.

### `RegretMatrix`
```python
rows: list[RegretRow]
  option_id
  regret_1y, regret_5y, regret_10y: int   # 0..5
  tell_a_friend_test: str          # would you be comfortable describing this?
  asymmetry: str                   # which direction of regret is worse
```
**Invariants** · every option scored at all three horizons.

### `IntegrityCheck`
```python
requires_becoming: list[Becoming]  # option_id, what kind of person, acceptable?
promises_broken: list[Promise]     # to whom, what, renegotiable?
```

### `InactionHarm`
```python
harm_of_delay: str
harm_of_status_quo: str
who_pays_for_inaction: list[str]
decay: str                         # what gets worse the longer this takes
```
**Invariants** · all fields non-empty. This stage exists **specifically to
counteract this module's own paralysis bias** — the ethicist must price inaction
before it is allowed to counsel caution. A structural fix for a known bias, which
is preferable to asking it in a prompt not to be biased.

---

## Shared terminal artifact

### `Conclusion`
Produced by exactly one stage per program — the terminal one. This is the only
artifact type in the registry with a `stance` field.

```python
stance: str                        # imperative, concrete, names the first action
first_action: str                  # doable within 48 hours
reasoning: str                     # prose, in the module's register, derived
                                   # from its artifacts — no new facts allowed
key_claims: list[ClaimRef]         # artifact row ids this rests on
confidence: Confidence
  score: float                     # 0..1
  basis: str
  falsifier: str                   # the ONE observation that flips this stance
what_would_change_my_mind: str
cheapest_decisive_test: str | None
ethical_veto: bool = False         # ethicist only; synthesis must address it
```
**Invariants** · `falsifier` non-empty and phrased as an observation, not a
feeling; `key_claims` must reference real row ids from this module's own
artifacts (the citation check — a conclusion resting on nothing is caught here);
`stance` must begin with a verb; `score ≥ 0.8` requires zero `assumed` or
`speculative` rows among the referenced `key_claims`.

That last invariant is the mechanical version of "never hallucinate confidence":
high confidence is *arithmetically unavailable* to a module whose own load-bearing
evidence is labelled an assumption.

---

## `Table` — the one artifact an authored module may shape (ADR-030)

Every kind above is defined in Python with a hand-written validator. A user-authored module
can write neither, so it gets exactly one generic kind and declares the constraints itself:

```yaml
produces: Table
table:
  columns: [precedent, mechanism, outcome_rate]
  min_rows: 3
  required: [precedent, mechanism]
  distinct: [precedent]
  required_tags: [ended_well, ended_badly]
  ranges: [{column: outcome_rate, minimum: 0.0, maximum: 1.0}]
  sums_to: {column: share, total: 1.0, tolerance: 0.02}
  covers: {stage: cast, column: person, into: person}
```

```
title: str
rows: list[TableRow]
  id: str                          # short, unique, citable
  cells: dict[str, str|float|int|bool|None]   # keyed by the declared columns
  tags: list[str]
```

**Invariants** · every declared rule above, plus: unique non-empty row ids; no column
outside `columns`. Each rule is a restatement of a shape the built-ins already assert —

| rule | the built-in it generalises |
|---|---|
| `min_rows` | `OptionSet` ≥7, `FailureModeTable` ≥3 |
| `required` | the psychologist's nine dimensions, non-empty every time |
| `distinct` | no two options may share a label |
| `required_tags` | `REQUIRED_OPTION_TAGS`; ADR-014's forced `reckless` option |
| `ranges` | the leaf-probability floor |
| `sums_to` | probability-tree siblings, flattened to one column |
| `covers` | `PersonProfileSet` must cover `PersonList` |

**The loader refuses a spec that cannot fire**, because such a spec reads as a guarantee: a
`required`/`distinct`/`ranges`/`sums_to` column absent from `columns`; a `covers` pointing
forward; a `table:` block on a stage producing something else; a spec with columns but no
constraint at all; and a `covers` pointing into the **same group** — grouped stages become one
call (ADR-013), so the covered artifact does not exist yet.

**What this cannot express**, stated rather than hidden: recursive structure (tree depth,
sibling sums over nesting) and cross-field semantics ("the ten-year regret must not contradict
the one-year row"). An authored module is therefore held to a real but weaker standard than
the six.
