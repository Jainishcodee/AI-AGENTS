# The council layer

Everything above a single module: which modules run, who critiques whom, what the
synthesiser is contractually required to produce, and how outcomes feed back into
future reasoning.

---

## 1. Presets

A **preset** selects modules and assigns each a role. It does not modify programs —
the same `AgentProgram` runs identically whichever preset invoked it.

```yaml
id: strategy
name: Strategy & Power
description: For decisions dominated by other people's interests and moves.
primary:   [tactician, strategist]     # full program, all stages, in the output
advisory:  [analyst]                   # full program, collapsed in the UI by default
critic:    [psychologist, ethicist, optimizer]   # critique only — no stage 1 run
```

Three roles:

- **`primary`** — runs its full program; its artifacts and conclusion are
  foregrounded in the UI and the trace.
- **`advisory`** — runs its full program; presented collapsed. Its conclusion still
  reaches the synthesiser at full weight.
- **`critic`** — does **not** run stage 1. It receives the primary and advisory
  artifacts and produces critiques only. Cost is one call instead of three, and
  its blind-spot detectors still fire.

The critic role is the important one. It is what lets you foreground two modules
without losing the checks that keep them honest — the psychologist can still catch
the strategist assuming everyone is strategic, without generating a full
nine-dimension profile set nobody asked for.

### Built-in presets

| preset | primary | advisory | critic | calls (`standard`) |
|---|---|---|---|---|
| `full` | all six | — | — | ~26 |
| `strategy` | tactician, strategist | analyst | psychologist, ethicist, optimizer | ~15 |
| `people` | psychologist, strategist | ethicist | analyst, tactician, optimizer | ~15 |
| `execution` | optimizer, analyst | tactician | psychologist, ethicist, strategist | ~15 |
| `life` | ethicist, psychologist | analyst | tactician, strategist, optimizer | ~15 |
| `solo:<module>` | one | — | the other five | ~9 |

`solo:strategist` is the "just give me the power map" mode: one full program plus
five cheap critiques. Roughly a third the cost of `full` and it still tells you
when the psychologist thinks the graph is fiction.

Presets are data (`apps/api/app/programs/presets/*.yaml`), so a user-defined
preset in Phase 5 is a row, and `DecisionCard` records which preset produced it —
required for fair calibration, since a module's accuracy in `critic` role is not
comparable to its accuracy in `primary`.

---

## 2. Critique routing

Critique is routed, not broadcast. Six modules × five targets = 30 critique
relationships, most of which are noise — the ethicist has nothing useful to say
about the analyst's arithmetic.

Routing is derived from the specs, not configured separately: module M critiques
module T if and only if `M ∈ T.critics`. The resulting matrix:

```
critic ↓ / target →   analyst  tactician  strategist  psychologist  optimizer  ethicist
analyst                  ·         ✓           ✓           ✓            ✓         ✓
tactician                ✓         ·           ✓           ✓            ✓         ✓
strategist               ·         ✓           ·           ✓            ·         ·
psychologist             ✓         ✓           ✓           ·            ✓         ✓
optimizer                ✓         ✓           ✓           ✓            ·         ✓
ethicist                 ✓         ✓           ✓           ✓            ✓         ·
```

`GET /critique-matrix` returns this, computed from the specs at runtime, so the
table above cannot silently drift from the code. `tests/test_loader.py` asserts
the two agree in both directions.

Each critique call gives the critic: the target's artifacts, the target's
**biases with `watch_for` detectors**, and its own `critique_lens`. It returns:

```python
Critique
  critic: ModuleId
  target: ModuleId
  target_ref: ArtifactRowRef | None   # kind + row id — the trace draws this edge
  kind: unsupported | missing_factor | wrong_frame | overweighted
      | bias_fired | boundary_violation | strong_agreement
  statement: str
  severity: int                        # 1..5
  bias_id: str | None                  # set when kind == bias_fired
```

`target_ref` is what makes the debate legible: a critique attached to
`StakeholderGraph.node:cto` renders as an edge into that node rather than as a
paragraph about disagreement. `strong_agreement` exists because independent
convergence is real evidence and deleting it would bias the record toward conflict.

Revision then returns, per module: accepted critiques (with what changed and why),
rejected critiques (with grounds), an updated stance, and updated confidence.
**Rejected critiques are kept and shown to the synthesiser** — an unresolved
disagreement between two modules that both held their ground is the single most
informative thing in a deliberation.

---

## 3. Synthesis contract

The synthesiser is the only component permitted to produce advice on behalf of the
council. It is not a summariser, and it is contractually forbidden from averaging.
It receives every artifact, every critique including rejected ones, every
falsifier, the preset, and the user's calibration history.

```python
Synthesis
  debate_summary: str                # what the disagreement was actually about
  consensus: list[ConsensusPoint]    # point + which modules + supporting row refs
  disagreements: list[Disagreement]
     issue, positions[{module, position}], why_it_matters,
     what_would_resolve_it, resolved_by: str | None
  blind_spots_fired: list[FiredBias] # bias_id, module, evidence, whether corrected
  council_blind_spot: str            # what NO module examined — see below
  recommendation: Recommendation
     action, first_action, timeline, do_not[], conditions[]
  confidence: Confidence             # score, basis, falsifier
  calibration_note: str              # how the user's history adjusted this
  ethical_veto_response: str | None   # MANDATORY when a veto was raised
  minority_opinions: list[Minority]  # module, position, when_it_would_be_right
  alternative_strategy: Alternative  # the second-best path, and its trigger
  long_term_prediction: list[Horizon] # 3mo / 1y / 5y, each with confidence
  information_to_gather: list[str]   # ranked by decision value, from all gaps
```

Enforced rules:

1. **Minority opinions may not restate the majority.** Similarity-checked against
   `recommendation.action`; too-close text is rejected and regenerated. Every
   module whose stance opposes the recommendation must appear here with a
   `when_it_would_be_right` condition — a falsifiable statement about the world,
   not a hedge.
2. **Falsifier discounting.** Where a module's `confidence.falsifier` has already
   been satisfied somewhere in the transcript, the synthesiser must discount that
   module and say so in `calibration_note`. This is the mechanism behind "never
   hallucinate confidence" (ADR-010).
3. **The veto must be answered.** `ethical_veto_response` is required whenever a
   veto was raised. It may disagree; it may not ignore.
4. **`council_blind_spot` is mandatory and may not be empty.** The synthesiser
   must name a dimension *no* module examined — the question behind the question,
   the option nobody generated, the party nobody counted. Six modules with fixed
   programs have fixed collective blindness, and the honest move is to state it
   rather than let structural coverage read as completeness.
5. **Confidence is bounded by the inputs.** `score` may not exceed the highest
   module confidence among the modules the recommendation actually follows.
   Synthesis cannot manufacture certainty that no participant held.
6. **Consensus points cite artifact rows.** Unsupported claims are rejected.

Model routing: synthesis uses the strongest available model. It reads ~15k tokens
of structured argument and commits to advice a person may act on — the one place in
the pipeline where model quality is not a cost trade-off.

---

## 4. Decision Cards

Every deliberation persists as a **Decision Card**: the unit of the product's
memory, and the reason it improves with use.

```python
DecisionCard
  id, user_id, project_id, created_at
  question, context: DecisionContext
  preset, depth, program_versions: {module: int}
  trace_id
  recommendation: Recommendation
  per_module: {module: (stance, confidence, falsifier, abstained)}
  expected_outcome: ExpectedOutcome
     statement: str            # falsifiable, concrete
     check_on: date            # set at write time
     measurable_by: str
  minority_opinions: list[Minority]
  # written later, by the user:
  resolution: Resolution | None
     chose: str                # what they actually did — often none of the options
     actual_outcome: str
     happened_at: date
     surprises: list[str]      # what nobody predicted
     notes: str
  scoring: {module: Verdict} | None      # right | wrong | partial | untested
```

Two design points carry the feature:

- **`expected_outcome` is written at deliberation time, and is falsifiable and
  dated.** This is what makes scoring possible at all. Written afterwards it is
  hindsight; written before, with a `check_on` date the card schedules itself, it
  is a prediction.
- **`resolution.chose` is free text, not an option id.** People do not pick from
  the menu. The most valuable rows in the corpus are the ones where the user did
  something no module proposed — that is a direct measurement of the council's
  option-generation blindness.

`program_versions` per module means an old card can always be replayed against the
exact program that produced it. Without it, changing a program silently invalidates
every historical score.

---

## 5. Calibration and learned priors

From resolved cards, computed per module **per user** (and separately per module
globally, once there is enough data):

| Metric | Definition |
|---|---|
| **Brier score** | mean squared error of stated confidence vs. binary correctness |
| **Hit rate** | share of `right` verdicts, by domain |
| **Execution rate** | share of recommendations the user actually acted on |
| **Metric-specific scores** | each module's own `success_metrics` from its spec |

Two honesty rules on display: nothing is shown before **n ≥ 8** resolved cards for
that module, and the horizon is stated alongside the number — the strategist's
90-day metrics mature long before the ethicist's 365-day ones, and showing them on
the same row would be a lie of presentation.

### Priors

Metrics become **priors** — natural-language patterns with evidence counts,
injected into `AgentMemory` at stage 1:

```python
Prior
  module, pattern: str
  evidence_count: int
  derived_from: list[CardId]     # always clickable back to the cards
  confidence: float
  domain: str | None
```

Examples of what the loop actually produces:

```
strategist  "In 4 of 6 resolved career decisions, the actor who actually blocked
             was one this user had not mentioned."               n=6
tactician   "Bold moves recommended to this user: 8 proposed, 3 taken, 2 worked.
             All 5 declined were tagged one_way."                n=8
optimizer   "Of 7 systems recommended, 2 survived 90 days. Both were single-rule
             changes requiring no new tooling."                  n=7
analyst     "This user's stated 80% outcomes have occurred 55% of the time."  n=11
```

Three rules keep this from becoming a feedback loop that eats itself:

1. **Priors are evidence, not instructions.** Presented with counts and card
   references. A module whose prior is contradicted by the current context must say
   so explicitly in its reasoning.
2. **Priors never alter a program.** They enter as memory, never as changed stages
   or changed instructions. Otherwise the module drifts and its historical scores
   stop meaning anything.
3. **A prior needs `evidence_count ≥ 3`** and must cite its cards. Two data points
   are an anecdote, and an anecdote injected as a prior is how a system becomes
   confidently wrong about a specific user.

This is the compounding asset. The six programs are copyable in an afternoon. Four
hundred resolved Decision Cards belonging to one person, with per-module accuracy
by domain, are not — and they are what turns a reasoning tool into *their* decision
engine.
