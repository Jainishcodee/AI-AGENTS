# Decision records

Short, dated, and honest about what we gave up. New decisions go at the bottom.

---

## ADR-001 — Agents are declarative data, not subclasses

**Decision.** An agent is a YAML file validated into an `AgentSpec`. There is no
`class KleinAgent`. Behaviour differences are expressed entirely as data:
`framework` steps, `artifact` shape, `critique_lens`, `blind_spots`, `voice`.

**Why.** Phase 5 is a marketplace for custom reasoning agents. If agents are
code, a user-created agent means executing user-supplied Python, and every new
council member is a deploy. If agents are data, a new agent is a row. It also
forces the cognitive algorithm to be written down explicitly rather than smeared
through a prompt string where nobody can diff it.

**Given up.** An agent cannot run bespoke logic — no calling a calculator, no
custom retrieval. When one genuinely needs that, the escape hatch is a `tools`
field on the spec naming capabilities the runtime provides, not arbitrary code.

---

## ADR-002 — Divergence is enforced by forced artifacts, not by personas

> *Extended by ADR-011: forced artifacts were necessary but not sufficient. The
> artifact must be produced by a separate execution, or the model can decide its
> conclusion first and back-fill.*


**Decision.** Each framework step must produce a named output, and each agent is
required to fill in a different structured artifact before stating a stance.

**Why.** Six personas over one model produce one answer in six voices. The
model's prior about the sensible answer is much stronger than a tone
instruction. A power map and an emotional ledger, filled in honestly, cannot
lead to the same conclusion.

**Given up.** Output tokens roughly double, and an agent occasionally fills the
artifact perfunctorily. The mitigation is in the critique stage: a thin artifact
is itself a valid critique target.

---

## ADR-003 — Blind spots are withheld from their owner

**Decision.** `blind_spots` never appear in the owning agent's reasoning prompt.
They appear in the other five agents' critique prompts, each with a `watch_for`
detector, and in the synthesiser's prompt.

**Why.** An agent told about its weakness performs the absence of that weakness.
"You overanalyse" yields a shallow answer relabelled as decisiveness. A blind
spot is only meaningfully caught from outside.

**Given up.** An agent cannot self-correct a known flaw in round 1. That is the
point — round 2 exists precisely to catch it, and the catch is now visible to
the user instead of happening invisibly inside one prompt.

---

## ADR-004 — Every agent output is validated JSON with one repair attempt

**Decision.** Agents return JSON conforming to a Pydantic model. On a validation
error, exactly one repair call is made showing the model its output and the
validator's error. A second failure raises and the agent is recorded as an
abstention.

**Why.** Critiques must target specific claims by id, disagreements must be
computed rather than vibed, and the UI must render an inspectable reasoning
chain. Free text supports none of that. And a hard failure is better than
silently downgrading to prose, which would make the deliberation quietly
shallower with no signal to anyone.

**Given up.** Latency and token cost of the occasional repair, and a hard
dependency on the model's JSON competence. Small models are therefore unsuitable
for the `reasoning` role, which is why routing is per-role.

---

## ADR-005 — Model routing by role, not by name

**Decision.** Three roles — `intake`, `reasoning`, `synthesis` — each map to a
`provider:model` string in config.

**Why.** Intake is classification and deserves the cheapest model; synthesis
reads ~15k tokens of argument and commits to advice, so it deserves the best.
Wiring model names into call sites makes that impossible to tune and impossible
to audit. Three env vars is the whole cost model of the product.

**Given up.** Per-agent model choice. `AgentSpec` has an optional
`model_override` for the case where one agent genuinely needs a different model,
but the default is uniform so that differences in output are attributable to the
framework rather than to the model.

---

## ADR-006 — Gemini free tier is the default route

**Decision.** Default routing is Gemini (`2.5-flash-lite` / `2.5-flash` /
`2.5-pro`), with OpenRouter free models as fallback and Ollama as a local
last resort.

**Why.** A standard deliberation is ~20 calls. During development that is
hundreds of calls a day, and a paid default would make iteration a budget
decision. Gemini's free tier covers development entirely, and the provider
abstraction means production routing is a config change.

**Given up.** Free-tier rate limits are per-minute and hit hard when six agents
fire at once, hence `COUNCIL_MAX_CONCURRENCY` defaulting to 4 rather than 6.
This trades ~15 seconds of wall clock for not being rate-limited.

---

## ADR-007 — No LangGraph yet

**Decision.** The orchestrator is a plain async state machine over an explicit
`DeliberationState`, emitting typed events.

**Why.** The Phase 1–3 pipeline is a DAG with one optional repeated stage. That
is a `for` loop. LangGraph earns its dependency when we need checkpointing,
cycles with history-dependent exit conditions, and human-in-the-loop
interrupts — Phase 4 territory. Adding it now buys flexibility we cannot use
and costs a layer of indirection over the part of the system we will iterate on
most.

**Given up.** A migration later. Kept cheap by making stages take and return the
state object and communicate only through it.

---

## ADR-008 — Persistence behind a protocol; no database in Phase 1

**Decision.** `MemoryStore` is a Protocol. Phase 1 ships `InMemoryStore` and a
JSON `FileStore`. Postgres + pgvector arrives in Phase 2 as a third
implementation.

**Why.** Docker, Postgres, and a migration tool on day one is a day of
infrastructure that produces zero reasoning quality. The expensive thing to
retrofit is the *shape* of the interface — especially per-agent `recall`, which
is not the same as one shared index — and that is defined now.

**Given up.** Nothing in Phase 1. In Phase 2 the `FileStore` gets deleted.

---

## ADR-009 — "Ethical manipulation" is bounded explicitly in the spec

**Decision.** Lumian's brief includes influence and psychological leverage. The
spec encodes an explicit boundary: permitted are framing, timing, selective
emphasis, creating optionality, and letting others draw their own conclusions.
Forbidden are deception, fabricated leverage, manufactured urgency, and
exploiting someone's crisis. The boundary is in the shared constitution too, so
it is not one agent's discretion.

**Why.** "Manipulation (ethical)" is a real and useful skill — negotiation and
persuasion are legitimate — but the phrase has no natural stopping point, and an
LLM asked to be cunning will find the stopping point uncomfortably late. Naming
the line in data makes it reviewable and testable. Leonard is also given
standing to veto on this axis, which is what makes the constraint structural
rather than decorative.

**Given up.** Some genuinely effective but dishonest tactics. Correct trade for a
product people are supposed to trust with real decisions.

---

## ADR-010 — Confidence must come with a falsifier

**Decision.** Every `Confidence` object requires `score`, `basis`, and
`falsifier`: the single observation that would flip the stance. The synthesiser
is instructed to discount any agent whose falsifier is already satisfied
elsewhere in the transcript.

**Why.** "Confidence: 85%" from an LLM is decoration. A falsifier is checkable,
gives the user their highest-value next action ("go find this out"), and turns
the calibration requirement into a mechanism instead of an instruction to be
humble.

**Given up.** Agents sometimes write a weak or unfalsifiable falsifier. That is
visible in the UI and is an explicit critique target, which is the best
available answer short of a separate verifier call.

---

## ADR-011 — An agent is an executed program, not a prompt (supersedes part of ADR-002)

**Decision.** A module is an ordered list of **stages**. Each stage is its own
execution with declared `reads`, a required output artifact type, and a non-empty
`must_not`. The runtime is a generic interpreter — `engine/` executes whatever
program it is handed and never references a module by name.

**Why.** ADR-002 said "forced artifacts". It was not enough, because one call
producing one large object still lets the model decide its conclusion first and
back-fill the artifact to match. Reasoning order is only real if it is an
execution order. Klein cannot advise before building the evidence ledger when the
ledger is a *prior call* whose output schema contains no stance field.

Second reason: every stage becomes independently inspectable, cacheable, and
re-runnable. "Re-run the strategist's leverage stage with this new fact" is a
supported operation rather than a full rebuild.

**Given up.** 6 modules × 7 stages ≈ 42 calls before critique. Addressed by
ADR-013, not by shortening the programs.

---

## ADR-012 — Artifact invariants are validated in code, not requested in prose

**Decision.** Every artifact type has a Pydantic model *and* an invariant
validator. Probability-tree siblings must sum to 1.0 ± 0.02. The stakeholder graph
must contain a `me` node and be connected. Every person in `PersonList` must have
all nine profile fields. Ratios are recomputed server-side rather than trusted.

**Why.** This is where rigor actually comes from. "Make sure your probabilities
are coherent" is advisory; `sum(p) == 1.0` is not. The arithmetic check catches
sloppiness that reads perfectly well in prose — which is the failure mode that
makes plausible LLM analysis dangerous.

It also relocates quality control from prompt engineering to type design, which
is testable, diffable, and does not regress when a model is swapped.

**Given up.** Validation failures cost a repair call, and strict validators
occasionally reject a defensible artifact. Accepted: a visible failure beats a
silently incoherent tree. Two consecutive failures record an abstention rather
than admitting a malformed artifact into the trace.

---

## ADR-013 — Program and plan are separate; depth changes the plan only

**Decision.** Stages declare a `group`. The **planner** turns a program plus a
depth setting into an execution plan: `quick` collapses a whole program into 1–2
calls, `standard` runs one call per group, `deep` runs one call per stage.
Artifacts are validated individually regardless of how many arrived in one
response.

**Why.** ~55 calls per question cannot be the only mode, but shortening the
algorithm to save money would defeat the point. Separating program from plan means
nothing is *skipped* at `quick` — the probability tree still gets built, it just
gets built in the same breath as the ledger. Rigor degrades gracefully; the
algorithm does not change.

**Given up.** Batched stages share context, so a later stage in a group can see
its predecessor being written and anchor on it. Two mitigations: `tactician.generate`
is never batched at any depth (divergence collapses when evaluation shares
context), and `deep` exists for decisions where the isolation matters.

---

## ADR-014 — Known biases are corrected with pipeline structure, not instructions

**Decision.** Where a module has a predictable bias, add a mandatory stage that
forces the counterweight artifact into existence. The ethicist must produce
`InactionHarm` — the harm of delay, of the status quo, who pays, what decays —
*before* its terminal stage. The tactician must produce an `OptionSet` carrying a
`reckless` tag before ranking.

**Why.** "Don't be overly cautious" produces a module that is cautious and then
appends a disclaimer. Requiring it to *price inaction as an artifact* changes what
it can conclude, because the terminal stage reads that artifact. The correction
becomes part of the reasoning rather than a note about it.

**Given up.** Programs get longer, and one stage per module exists to fight that
module rather than to analyse the problem. Worth it: these are the biases most
likely to make advice actively harmful.

---

## ADR-015 — The Thinking Trace is derived from execution, never generated

**Decision.** The trace graph is constructed from the execution record: nodes are
validated artifacts, `derives_from` edges come from each stage's declared `reads`,
`critiques` edges come from `Critique.target_ref`. Layout is computed client-side
from graph depth. No LLM call produces any part of it.

**Why.** A reasoning diagram an LLM wrote *about* its reasoning is theatre — it can
be tidy and wrong, and it can omit the step that actually drove the conclusion.
Deriving it means the map cannot disagree with the territory. It also means the
same deliberation always renders identically, and every node is clickable down to
the artifact that produced it.

**Given up.** The trace shows the *structure* of reasoning, not free-form insight
about it. Correct trade — the artifacts already carry the content.

---

## ADR-016 — Modules and skins are separate; the engine sees only modules

**Decision.** Every program declares `module` (`analyst`, `tactician`,
`strategist`, `psychologist`, `optimizer`, `ethicist`) and a separate `skin`
(name, title, accent). Engine, trace, calibration tables, and synthesiser
reference `module` exclusively.

**Why.** The LOTM layer is what makes this fun to build and legible to explain,
and it is a liability the moment the product meets a stranger who has not read the
books. Making the skin a presentation config means dropping or reskinning it is
deleting one file, and it means calibration data — the durable asset — is keyed to
`strategist`, not to a character name. It also opens room for modules with no skin
at all: `economist`, `lawyer`, `historian`, `adversary`.

**Given up.** Slight indirection in the UI layer. Negligible.

---

## ADR-017 — Presets select modules and assign roles; programs are never modified

**Decision.** A preset assigns each module a role: `primary` (full program,
foregrounded), `advisory` (full program, collapsed), or `critic` (critique only,
no stage-1 run). `DecisionCard` records the preset.

**Why.** Users care about some modules more than others, and running all six at
full depth for every question is neither affordable nor wanted. But dropping a
module is a trap, because the critics are what keep the favourites honest — the
psychologist is the strongest check on the strategist's assumption that people are
strategic. The `critic` role costs one call and preserves the check.

Recording the preset on the card is required for fair calibration: a module's
accuracy in `critic` role is not comparable to its accuracy in `primary`.

**Given up.** More configuration surface, and a calibration corpus partitioned by
role, which needs more resolved cards before per-module numbers mean anything.

---

## ADR-018 — Priors are injected as evidence and never modify a program

**Decision.** Calibration produces natural-language `Prior` records with an
`evidence_count` and the card ids they derive from. They enter stage 1 as
`AgentMemory`, attributed and countable. They require `evidence_count ≥ 3`. They
never alter stages, instructions, or behaviour parameters.

**Why.** This is the compounding asset and the easiest thing to get catastrophically
wrong. A system that rewrites its own prompts from its own scoring drifts, and its
historical scores stop being comparable — you lose the ability to tell whether the
module improved or the yardstick moved. Keeping the program fixed and the memory
variable means every score in the corpus remains meaningful.

Presenting priors as citable evidence rather than instruction also lets a module
argue with them, which is required — a prior contradicted by the current context
should lose.

**Given up.** Slower adaptation than prompt-tuning on outcomes would give. Bought:
an audit trail, comparable scores across time, and no silent drift.

---

## ADR-019 — An explicit `null` means "not supplied", not "invalid"

**Decision.** `schemas.common.Strict` runs a pre-validator that replaces an explicit
`null` with the field's default, for any optional field **not** declared nullable.
Fields typed `X | None` keep their null, because there the null is meaningful.

**Why.** Found in the first live run: the synthesiser returned
`"calibration_note": null` — meaning "nothing to say here" — and the whole
synthesis failed validation. That is the wrong trade twice over. The field has a
default and the intent is unambiguous, so failing is pedantry; and the repair call
it triggers costs a request against a per-minute quota that is the binding
constraint on the entire product.

The distinction is doing real work: it fixes the noise case without weakening any
invariant. `veto_grounds: str | None` still round-trips its null, so
"veto raised with no grounds" is still catchable.

**Given up.** A model that genuinely meant to signal something by `null` on a
defaulted field is silently reinterpreted. No such case exists in the schema.

---

## ADR-020 — Pace requests per minute, not just concurrently

**Decision.** `llm/registry.py` carries two independent limits: a semaphore for
in-flight calls (`COUNCIL_MAX_CONCURRENCY`) and a sliding-window limiter for calls
per minute (`COUNCIL_MAX_RPM`). 429 backoff has its own schedule, starting at 12
seconds rather than 1. The mock provider is exempt from pacing.

**Why.** Also found in the first live run, and it invalidated an assumption in
ADR-006. Free tiers meter **requests per minute**; a semaphore caps how many are in
flight, which is a different quantity. Three concurrent calls finishing in two
seconds each is nine requests a minute, and the limit observed on this key was
five. Worse, the standard 1-2-4 second exponential backoff retries three times
*inside the same one-minute window* and fails all three — the retry policy was
structurally incapable of recovering from the error it existed to handle.

Two further findings from the same run, recorded because they will bite again:
`gemini-2.5-pro` is not on the free tier at all (429 with `limit: 0`, so the
synthesis route had to move to flash), and a per-minute cap means a 26-call
`standard` deliberation takes minutes of wall clock on a free key regardless of how
fast the model is. That is the real argument for the `critic` role in ADR-017 and
for `quick` depth — they are not just cost features, they are what make the product
usable without a card on file.

**Given up.** Wall-clock latency, deliberately. The alternative is a deliberation
that reliably half-fails, which is worse than one that is slow.

---

## ADR-021 — The grader is blind to confidence; the arithmetic is not its job

**Decision.** Grading a resolved decision is split in two:

- `learning/grader.py` — one LLM call that judges **what happened**: a verdict per
  module (`right` / `wrong` / `partial` / `untested`), whether the user acted on that
  module's advice, whether its falsifier fired, and whether what they chose was even
  on the table. It is shown every stance and every falsifier, and **never** any
  module's confidence score.
- `learning/scoring.py` — pure Python that turns those judgements into Brier scores,
  hit rates and execution rates, using the confidence stored on the card.

`learning/priors.py` then phrases patterns from those numbers using string templates.
**No model ever writes a count.**

**Why.** If the grader can see "the analyst was 90% confident", that leaks into
whether the analyst is marked right, and the Brier score becomes a measurement of
itself. Withholding confidence is what makes calibration mean anything — being sure
and being right have to be measured independently or neither is measured.

The second half matters as much. A sentence like *"your stated 80% has occurred 55%
of the time"* is only worth injecting into a module's prompt if the two numbers are
real. Computing them in Python and filling a template guarantees that; asking a model
to summarise its own scoring would produce the same sentence with invented figures,
and the entire calibration story would be theatre.

Two supporting constraints:

- **`untested` is a first-class verdict**, and the prompt pushes toward it. Marking a
  module `right` because the outcome was good, when the user never took its advice,
  is the easiest way to corrupt the corpus. Untested observations are excluded from
  accuracy but still count against execution rate, because "you never took this" is
  itself a measurement.
- **The grader must cover every participating module or it fails.** A silently
  missing verdict would drop that module out of its own history, which is worse than
  a visible error.

**Given up.** The grader cannot use confidence as a signal about how carefully a
module reasoned, which is occasionally real information. Correct trade: it is
indistinguishable from bias, and it is the one input that would invalidate the
output. A human can override any verdict (`overridden: true`), which is the intended
escape hatch — the user is the final judge of their own life.

---

## ADR-022 — Re-running derives a new deliberation; it never edits the old one

**Decision.** `rerun_stage` (one module from one stage, with new facts) and `refine`
(answer the open unknowns and deliberate again) both produce a **new** `Deliberation`
carrying `derived_from` and a `Rerun` record. The original is immutable.

On a stage re-run, critiques *of* the re-run module are dropped — they targeted
artifacts that no longer exist — while critiques *by* it are kept, because its reading
of the others did not change. Synthesis always re-runs.

**Why.** The reasoning record is the product. It is what Decision Cards are scored
against, what `program_versions` exists to make replayable, and what the Thinking
Trace is a view of. Editing it in place would mean a card could be graded against a
transcript that no longer matches the advice the user actually acted on — silently
corrupting the one dataset that cannot be regenerated.

Deriving instead also gives the history for free: a chain of `derived_from` links is a
readable account of how the decision was refined as facts arrived, which is more
useful than a single record that quietly improved.

**Why `refine` is a full re-deliberation** rather than a surgical patch: once a
load-bearing unknown is answered, every module's reasoning downstream of it is
suspect. Patching only the stages that mentioned it would produce a record that is
half-informed without saying which half.

**Given up.** Storage — a refined decision costs a second full transcript — and the
possibility of a cheap incremental update. Also more calls: a stage re-run is
`(stages after the cut) + synthesis`, not one call. Accepted: the alternative is a
mutable history, and a mutable history makes Phase 3 meaningless.

---

## ADR-023 — Lexical recall before vector recall

**Decision.** `MemoryStore.recall` ranks by term overlap weighted by salience and
recency. No embeddings. The pgvector column stays in the Phase 2 schema, unused until
there is a demonstrated query that lexical filtering misses.

**Why.** Three reasons, in order of weight:

1. **The corpus is tiny.** A heavy user generates a few hundred memories a year.
   Approximate nearest-neighbour search is a solution to a scale problem that does
   not exist here, and at this size the whole relevant set can simply be filtered.
2. **The useful keys are structured, not semantic.** "Decisions involving my manager",
   "career decisions this year", "cards where the tactician was wrong" — those are
   predicates, and predicates are more precise than cosine similarity. Semantic
   search actively misfires on this data: two unrelated decisions that share
   vocabulary surface as relevant.
3. **The intelligence is in extraction, not retrieval.** What makes the psychologist's
   recall feel like *that module* remembering is that it extracted emotional facts
   under its own rule — six stores with six extraction biases (`learning/extraction.py`).
   Swapping the ranking function would not change that; removing the extraction rules
   would destroy it.

Note also that **priors do not involve retrieval at all** — they are statistics
computed over the whole corpus. The part of memory that actually changes reasoning was
never a retrieval problem.

**Where retrieval genuinely earns its place** is elsewhere: grounding the analyst's
`BaseRateTable`, which currently must label unsourced statistics `guessed` with
`applicability ≤ 0.5`. That is a real quality gap, and the existing invariant —
`given` rows require a `source` — already shapes it correctly: retrieved facts enter
as **sourced artifact rows**, not as context appended to a prompt.

**Given up.** Recall misses paraphrases with no shared vocabulary. Mitigated by
surfacing any memory with `salience ≥ 0.7` regardless of overlap, so a standing fact
like "this user never gets anything in writing" reaches decisions that share no words
with the one it came from.

---

## ADR-024 — SQLite, not Postgres or MongoDB (supersedes ADR-008's Phase 2 plan)

**Decision.** Phase 2 persistence is SQLite: one file, WAL mode, versioned migrations
via `PRAGMA user_version`, and FTS5 with BM25 for recall. `FileStore` survives only as
a migration source (`app.cli migrate`); `InMemoryStore` remains for tests.

The shape is **filter in SQL, hydrate with Pydantic**: the fields actually queried on —
`check_on`, `resolved`, `graded`, `module`, `created_at` — are denormalised into
columns, while the whole validated model lives in a `doc` JSON column. Duplicating the
Pydantic schema in DDL would give two definitions that drift.

**Why not Postgres,** which ADR-008 planned for: the only thing it brought over SQLite
here was pgvector, and ADR-023 had already ruled vectors out until there is a query
lexical search demonstrably misses. Everything else it offers — concurrent writers,
network access, horizontal scale — belongs to a phase with actual users. `user_id` is
already on every schema for that day.

**Why not MongoDB,** which is the better *document* fit and was available on this
machine: `mongod` runs permanently and WiredTiger reserves a cache of
`max(256MB, half of RAM − 1GB)`, on a machine already at 88% full. And its local
edition has no vector search either — Atlas Search is Atlas-only — so the recall story
would have been the same text indexing, for the price of a resident service.

---

## ADR-025 — A replay must not be able to read its own answer

**Decision.** `POST /cards/{id}/replay` re-decides a resolved card against today's
programs and grades the result against the outcome that actually happened. For the
duration of that run, **every memory extracted from that card and every prior computed
from it is withheld** — `MemoryStore.recall` and `.priors` both take an `exclude_cards`
set. The response reports how many of each were withheld.

**Why replay exists at all.** ADR-018 forbids the system tuning itself from its own
scoring, which leaves an obvious question: how do you ever improve a module? The answer
is this. With the outcome already known, re-running an old decision measures whether a
changed program would have done better. It turns the resolved corpus into a test set for
the council itself — deliberate, measured, human-initiated change instead of drift.

**Why the guard is load-bearing rather than tidy.** Memories extracted from a card
*describe what happened*: "the offer arrived nine days later" is a memory the analyst
would be handed while being asked to predict whether the offer arrives. Priors computed
from the card encode the verdict directly. Without the exclusion, a replay scores well by
reading the answer, and every backtest is worthless while looking rigorous — which is
worse than having no backtest, because it would be believed.

**Reporting the withheld count** matters for the same reason. A replay that excluded
nothing is not evidence of a clean run; it may mean nothing was extracted from that card
in the first place. Surfacing the number lets the result be weighed rather than trusted.

**Given up.** The replay is slightly *worse* informed than a fresh deliberation today
would be — it cannot use legitimate general knowledge that happens to have come from this
card. Correct trade: a pessimistic measurement is usable, an optimistic one is not. It
also means a replay is not a prediction of what the council would say now, only of what
it would have said then; the distinction is worth keeping in mind when reading one.

**Also enforced:** the original card and deliberation are never mutated by a replay
(ADR-022), and the replay's grading writes to a throwaway card so the original's scoring
history survives untouched.

---

## ADR-026 — Divergence is measured, and the instrument is tested against failures

**Decision.** The claim that these are six algorithms rather than six voices is
falsifiable, so `learning/divergence.py` measures it. Split by cost: a **structural**
half that reads only the specs (artifact distinctness, critique topology, bias-detector
coverage) and runs in CI on every commit; and a **behavioural** half that runs a fixed
eight-decision battery and is opt-in, because on a free tier it is minutes and real
quota.

**Why measure at all.** ADR-002 asserts that forced artifacts produce divergence and
ADR-011 asserts that separate executions make it real. Those are claims about the system,
and until this existed the only evidence for them was that the output *read* as different
— which is exactly the impression a well-written persona produces without any of the
machinery. A product whose central claim rests on an impression has no central claim.

**Reusing synthesis rather than building a second detector.** Dissent is counted from
`minority_opinions` and `disagreements`, and critique yield from `Revision.accepted` —
all of which synthesis already produces. A separate disagreement detector could
contradict the first, and then neither would be trustworthy. The cost is that a lazy
synthesis under-reports divergence, so **stance similarity** is included as the one
independent signal: crude word overlap, computed from the text, needing no judgement.
`LIMITATION` is printed in every report rather than buried here.

**The part that matters most is that the harness fails things.** An instrument only ever
pointed at a passing case is not known to detect anything, so the tests construct a
cloned module, a module nobody critiques, one that never dissents, one whose critiques
are never accepted — and run the harness against the **mock council**, whose six modules
genuinely are one voice. It reports 1.00 stance overlap and fails all six. That result is
the evidence the instrument works; without it the passing score on the real six would
mean nothing.

**Given up.** Word overlap is a poor semantic measure and will occasionally call two
genuinely different stances similar because they share vocabulary. Accepted: the
alternative is an LLM judge, which needs its own calibration, costs a call per pair, and
could be wrong in ways nobody would notice. A cheap check that cannot be gamed by
phrasing beats an expensive one nobody audits. The threshold (0.6) is a floor for
catching collapse, not a target to optimise.

**One structural finding worth recording.** `strategist` is critiqued by five modules but
critiques only two. That is per its spec and defensible — its concerns barely intersect
with the analyst's or optimizer's — but it means the module holding the most authority
over "who really decides" is the least active check on others. Worth revisiting if its
calibration scores come in weak.

**The argument that actually decided it:** SQLite is the only one of the three whose
storage layer can be **verified in CI against a real database**. `tests/test_sqlite_store.py`
opens a temp file and exercises migrations, status filtering, BM25 ranking, trigger-
maintained FTS deletes, timezone round-tripping, and migration idempotence — in about
two seconds, with no service and no fixtures to stand up. A database layer nobody can
run in tests is a database layer taken on trust, and this one holds the corpus that
Phase 3 makes the product defensible with.

**Given up.** Single-writer concurrency (fine: one user, and WAL keeps readers
unblocked), no network access, and no vector index. When there are real users the
`MemoryStore` protocol makes Postgres a swap rather than a rewrite — which is exactly
what ADR-008 was actually protecting, and it still holds.

**One correctness detail found the hard way.** Every `ORDER BY created_at DESC` carries
`rowid DESC` as a tie-breaker, and the in-memory store tie-breaks on insertion order.
Windows' clock advances in ~15.6 ms steps, so several decisions taken in one burst share
an identical `created_at` — and with the tie unbroken, "newest first" silently returned
the *oldest*. It surfaced as a flaky test rather than a failing one, which is the usual
way a real ordering bug announces itself. `tests/test_store_ordering.py` pins the
behaviour across all three stores, including that an update (recording an outcome on an
old card) must not reorder history.

**Also given up, deliberately:** hand-rolled term overlap in Python, replaced by FTS5.
Stemming now works — "negotiating" finds "negotiation" — and BM25 ranks better than my
count-and-weight did. One correctness detail worth naming: user text is never
interpolated into a `MATCH` expression. Every term is extracted and quoted, because raw
text containing `AND`, `NEAR`, `*` or `-` is valid FTS syntax and would silently mean
something other than what the user asked.

---

## ADR-027 — Resumption is a checkpointed program counter, not a graph runtime

**Decision.** A deliberation that dies mid-flight is saved as a `Checkpoint` — the request,
the intake context, the completed `ModuleRun`s, the *partial* runs of modules that got some
way through, the round counter, injected facts and accumulated usage — and resumed by
handing each module back its own artifacts and restarting at the first stage it had not
finished. `RESUMABLE_PHASES` names the four phases where partial work is worth keeping.
Nothing about the algorithm changes on resume.

**Why this closes the LangGraph question rather than deferring it a fourth time.**
ADR-007 deferred LangGraph and named the trigger explicitly: *execution surviving the
process*. That has now arrived, and it turned out to cost a Pydantic model, one SQLite
table and a `resume_from` argument on `run_program`. The reason is ADR-011. Because a
module is an ordered list of stages and every stage's output is a separately validated
artifact, the resume point is fully described by *which artifacts exist* — there is no
interpreter state to serialise, no closure, no pending coroutine. The program counter is
derivable: `next_stage_for` looks at what the run already produced and returns the first
stage that is missing.

A graph runtime checkpoints because its state is opaque; ours is a list of validated
documents in a table. Adopting LangGraph now would mean re-expressing six programs in
someone else's control flow to gain a persistence mechanism we already have, and taking on
their release cadence for it. **So this is not a fourth deferral — the trigger fired and
the answer was no.** If a future module needs genuine cycles with unbounded backtracking,
reopen it; the critique/revise round loop is a bounded `for`, and a bounded loop is not a
reason to import a graph.

**The bug this exposed, which mattered more than the feature.** Before checkpointing, a
provider outage was indistinguishable from six modules choosing to abstain: `ProviderError`
was caught by the same handler as `ArtifactInvalid`, so a quota exhaustion produced a
"complete" deliberation with six empty runs, a synthesis over nothing, and a Decision Card
written to the corpus. That card would then have been recalled as evidence and graded on
resolution — the learning loop poisoned by an outage. So the handlers are now split:
`ArtifactInvalid` still abstains, because a module that cannot produce a valid artifact has
genuinely failed to think; `ProviderError` raises `ProviderUnavailable`, which **carries the
partial run** so banked stages survive the exception.

**Ordering, which was wrong on the first attempt.** The gather over modules must bank every
successful `ModuleRun` and every non-empty partial *before* re-raising the outage. Raising
on first sight of the exception discards the work of every module that succeeded in the
same batch — precisely the work the feature exists to protect. On a free tier that is the
difference between resuming with five modules done and resuming with none.

**The exit criterion had to be run in two processes, and that is what found the real bug.**
`tests/test_resume.py` passed against `InMemoryStore`, which proves the resume *logic* and
says nothing about durability. Running `scripts/phase4_exit.py` — one process crashing on a
simulated 429, a second, separate interpreter picking the checkpoint up — surfaced two
things no test would have:

1. `FileStore` subclasses `InMemoryStore` and had not overridden `save_checkpoint`, so under
   the legacy JSON store every checkpoint lived in RAM and was gone on restart. Silently:
   `list_checkpoints` came back empty, which reads as "nothing was interrupted" rather than
   "your work was lost". `save_project` had the same defect, from the same cause.
2. The shipped `.env` and `.env.example` still said `COUNCIL_STORE=file` with a comment
   about Postgres, left over from before ADR-024 — so the *documented* default (SQLite) was
   not the default anybody actually ran.

Both are now fixed, and `tests/test_checkpoint_durability.py` re-opens each durable store
over the same directory rather than trusting the write. It also asserts the *class* of bug
away: any new write method on `InMemoryStore` that `FileStore` does not override fails the
suite by name, because inheriting a RAM-only write is worse than not having one.

The general lesson is worth more than either fix: an in-memory double cannot test a claim
about surviving the process, and a passing suite made it look like it had.

**A second pass over the same code found six more, five of them silent.** Worth listing,
because they share one shape — the checkpoint's *bookkeeping* disagreeing with reality
while every existing test passed:

1. **Double-banked module runs.** Banking successes before re-raising an outage (the fix
   above) left the original banking loop in place, so `checkpoint.completed` held every
   module twice and `checkpoint.usage` counted every call twice. Invisible on a fresh run,
   because `deliberation.runs` is built separately — and then every module appeared twice in
   the transcript the moment anyone resumed. The reported cost, which is what a person
   reads before deciding whether they can afford to continue, was roughly doubled.
2. **A provider outage during *synthesis* was still swallowed.** The reasoning phase learned
   the `ProviderError`/`ArtifactInvalid` distinction; synthesis did not. By then all six
   modules have run, so a 429 on the final call returned "no synthesis", completed the
   deliberation, wrote no card, and **deleted the checkpoint** — discarding ~26 calls at the
   single most expensive moment, with no resume offered. A `ValidationError` there still
   degrades, because an unusable answer genuinely is a synthesis failure.
3. **Critique history duplicated, then lost.** The copy of banked critiques into the
   deliberation sat *inside* the round loop: `deep` replayed round one on top of round two,
   and resuming with all rounds already done skipped the copy entirely, so the transcript
   claimed nobody had critiqued anybody. One statement moved above the loop fixes both.
4. **Injected facts did not survive a resume.** `Checkpoint.injected` was declared and never
   written to or read from. Facts were folded into the executor's *local* context, so they
   reached only the modules running at the time; after an interruption the person had
   answered the council's unknown and the resumed run behaved as though they had not.
5. **Preset and depth were re-resolved from settings on resume.** A request naming no preset
   falls back to the current default, so changing `COUNCIL_DEFAULT_PRESET` between the crash
   and the resume would continue a deliberation with a different set of modules than the
   banked artifacts came from — the same hazard the intake skip exists to avoid.
6. **`POST /council/resumable/{id}/resume` returned 200 for an unknown id.** The lookup lived
   inside the `StreamingResponse` generator, which does not execute until after the status
   line has gone out. The sibling `deliberate` route already validated first; this one
   deviated. It was the *only* route with no HTTP-level test, which is exactly why.

Also fixed while in there: the checkpoint write in the failure handler bypassed
`_checkpoint`, so a failing store could replace a quota error with a disk error and swallow
the re-raise; `_checkpoint` now returns whether it landed, so nothing announces "saved,
resume later" when the write failed.

**What generalises.** Five of the six were invisible because the checkpoint is written on
the failure path and read on the resume path, and almost every test exercised one or the
other but never both against real storage. `tests/test_pipeline_bookkeeping.py` asserts the
accounting directly — each module once, cost not inflated, `deep` costing exactly two rounds
rather than three — and targets induced failures **by role** rather than by call index,
because counting calls to land on "the synthesis one" silently lands in the revision phase
instead, where failures are caught and logged and the test passes for the wrong reason.

**Given up.** Resumption is per-stage, not per-token: a module interrupted halfway through
generating one artifact re-runs that stage from the start. Finer granularity would mean
persisting partial model output, which is not a validated artifact and therefore not
something the engine is allowed to hand to the next stage. Checkpoints are also not
garbage-collected on a schedule — `discard` is explicit, because silently deleting a
deliberation someone intended to resume is worse than a stale row.

---

## ADR-028 — Voice is a summarisation problem, not a text-to-speech problem

**Decision.** `python -m app.cli brief` produces a **script** first — the recommendation,
its falsifier, up to three dissents *in the dissenting module's own voice*, any ethical
veto, and the council blind spot — and only then synthesises audio. The full transcript is
never read aloud.

**Why not read the deliberation.** Six full analyses are a *reading* artefact. They are
tables, stakeholder graphs, probability trees and cited rows, and none of that survives
being spoken: "analyst slash evidence slash EvidenceLedger hash e one" is not a sentence.
Piping the transcript into a voice yields twenty-plus minutes nobody finishes, which is a
worse outcome than having no audio at all — it makes the feature look shipped while being
unused. The briefing is ~90 seconds, which the tests enforce as a bound
(`20 <= estimated_seconds <= 180`) rather than a hope.

**Dissent is the reason the feature exists.** A single narrated recommendation is a
notification read out loud. Six distinguishable voices disagreeing is the product's actual
argument made audible, so each minority opinion is spoken by its own module together with
the condition under which it would have been right. Voices are keyed by **module**, not
skin (ADR-016), so dropping the LOTM layer cannot silently reassign anyone's voice. Dissent
is capped at three and the remainder is explicitly acknowledged — beyond three it stops
being listenable, and silently dropping them would make the council sound more unanimous
than it was.

**Free, and degrading rather than failing.** `edge-tts` is a pip package against a public
Microsoft endpoint: no key, no card, and a large enough voice inventory to make six modules
sound like six people. ElevenLabs is better and costs money, so it is a config swap rather
than the default. If no engine is installed, `synthesise` returns `None` and the script is
still produced — the script is the half that carries the thinking and it is fully testable
without a network. MP3 frames concatenate byte-wise, so joining the parts needs no ffmpeg
either.

**One ordering detail worth recording.** `_speakable` strips row references *before*
markdown, not after. Stripping markup first removes the `#` and `_` characters, and a
citation with those gone (`analyst/evidence/EvidenceLedgere1`) no longer matches any
reference pattern — so it survives into the script and gets read out. Caught by the test
that asserts no `/` reaches the speaker.

**Given up.** No timing marks, so the UI cannot highlight the trace node being discussed.
That needs word-level timestamps, which the free endpoint does not return, and the reading
view already exists for anyone who wants the detail.

---

## ADR-029 — Responsive web and a PWA manifest, not a native app

**Decision.** Mobile is the existing Next.js app made genuinely usable on a phone, plus a
web app manifest with shortcuts straight to the two things worth opening on a phone:
`/history?status=due` and `/calibration`.

**Why.** The phone job is not deliberating — it is **resolving a due card**, which is the
one action the learning loop cannot proceed without and the one most likely to be done
while away from a desk. Nothing about that needs a native runtime: it is a form, a date and
some text. A React Native or Flutter client would duplicate every screen and the
`lib/types.ts` mirror for one form, and that mirror is already the thing most at risk of
drift (`test_web_contract.py` exists because it drifted twice).

**What actually changed, since "responsive" usually means nothing was tested.** The grid
was `minmax(420px, 1fr)`, which overflows any phone — now `minmax(min(420px, 100%), 1fr)`.
Nav scrolls horizontally instead of wrapping into two rows. Buttons and inputs get
thumb-sized padding below `sm` and tighten up above it. Mobile text inputs are `text-[15px]`
because iOS Safari zooms the viewport on focus at anything under 16px, and a zoom the user
has to pinch back out of is enough friction to abandon a resolution form.

**Given up.** No push notifications for due check-ins, which is the one genuinely native
capability that would matter here — web push needs a service worker, a VAPID key pair and a
subscription store, and the nav badge plus `pending_checkins` over MCP covers the same need
until there is more than one user. No offline caching: every screen is a live read of a
corpus that only exists on the machine running the API.

---

## ADR-030 — A user-authored module is a stored `AgentProgram`, loaded leniently and quarantined on error

**Decision.** A user module is *the same* `AgentProgram` the engine already executes — no
second schema, no parallel interpreter. It differs in exactly two ways: it is stored in
SQLite rather than read from YAML in the package directory, and it is loaded **leniently**.
A user module that fails validation is quarantined — recorded with its errors, excluded from
every preset, and reported — never fatal.

**Why not the existing load path.** The loader's loudness is deliberate and load-bearing: a
malformed *built-in* program refuses to let the server start, because a broken built-in is a
developer error and failing halfway through someone's deliberation is worse. That reasoning
inverts for user content. The person who authored the broken module is the person running
the process, a half-finished draft is the normal state of authoring, and a draft that
prevents the server booting takes away the only tool they have for fixing it. So built-ins
keep `ProgramInvalid`; user modules get a status and an error list.

The two rules therefore split:
- **Built-in, malformed → refuse to boot.** Unchanged.
- **User module, malformed → quarantine, keep serving.** The catalog reports it.

**The real obstacle was loader rule 4**, not storage: every `stage.produces` must name a
registered artifact type *that has a Python invariant validator*. That rule is the whole
reason these are six algorithms rather than six personas (ADR-012) — "instructions are
advisory, validators are not". A user cannot write a Pydantic model or a validator function,
so taken literally rule 4 makes user modules impossible. Three ways out:

1. **Reuse existing artifact kinds only.** Safe and nearly free, but a new module could only
   *recombine* — a new ordering of other people's artifacts. It could not force a new kind of
   thinking, which is most of what makes a module a module.
2. **Let users supply arbitrary JSON Schema.** Maximum freedom, nothing machine-checked
   beyond shape. This is precisely the persona-with-a-prompt that the project exists to
   reject, and it would quietly repeal ADR-012 for exactly the modules with the least
   scrutiny behind them.
3. **A generic table artifact with a declarative invariant vocabulary.** Chosen.

**Why the vocabulary is credible: it was extracted, not invented.** The ~40 hand-written
validators in `engine/invariants.py` are almost all instances of about eight recurring
shapes. The declarative rules are those shapes, and each one already has a built-in using it:

| declarative rule | already used by |
|---|---|
| `min_rows` | `OptionSet` (≥7), `FailureModeTable` (≥3) |
| `required_columns` (non-empty per row) | the psychologist's nine dimensions |
| `distinct` | no two options may share a label |
| `required_tags` | `REQUIRED_OPTION_TAGS` on the option set |
| `covers` a prior artifact's column | `PersonProfileSet` must cover `PersonList`; `AsymmetryTable` must cover `OptionSet` |
| `range` on a numeric column | the leaf-probability floor |
| `at_least_one_tagged` | ADR-014's forced `reckless` option |
| `sums_to` within a group | probability-tree siblings |

If the vocabulary can express what the built-ins already assert, it is expressive enough to
hold a user module to a real standard rather than a stylistic one.

**Shipped, and the expressiveness claim is now a test.** One artifact kind, `Table`, plus a
`TableSpec` on the stage that produces it. `tests/test_table_vocabulary.py` restates
`OptionSet`'s real invariant — the most demanding hand-written one, ≥7 options with five
required tags and no two labels alike — declaratively, and shows the declarative version
rejects each violation the Python one does. Every rule is also tested in *both* directions,
because a declarative rule that never fails is decoration.

**Three rules turned out to be about the loader, not the runtime.** A spec can be wrong in
ways that make it look like a guarantee while enforcing nothing, so the loader refuses:
a `required`/`distinct`/`ranges`/`sums_to` column that is not in `columns` (the rule could
never fire); a `covers` pointing forward; a spec on a stage that produces something else
(it would be silently ignored); and a spec with columns but *no* constraint — a table with no
rules is the persona-with-a-prompt case wearing a table for a hat.

The subtlest one: **`covers` may not point into the same group.** Grouped stages become one
call (ADR-013), so the covered artifact does not exist when the covering one is produced and
the check silently never runs. It costs an extra call per coverage rule, which on a free tier
is a real price — paid because a cross-stage guarantee that cannot fire is worse than none.
This caught a bug in the shipped example module, which had both tables in one group.

**Given up, and stated rather than hidden.** The recursive invariants do *not* generalise:
tree depth and sibling sums over a nested structure stay built-in-only, so a user cannot
author a probability tree. Declarative rules also cannot express cross-field semantics ("the
regret at ten years must not contradict the one-year row"), which is where the built-ins'
hand-written validators still earn their keep. A user module is therefore held to a weaker
standard than the six — knowable, checkable, but weaker — and the divergence harness
(ADR-026) is what stops that gap turning into a module that merely agrees eloquently.

**Two bugs the mock provider found, both real.** `synth.py` unpacked `get_args(annotation)`
into a single name, so the first artifact field annotated `tuple[X, ...]` rather than
`list[X]` raised `ValueError` and surfaced as an unexplained module abstention. And a batched
prompt contains every stage's declared shape, so a fixup reading the whole prompt filled the
second authored table with the first one's columns — the mock now scopes the prompt to one
stage's section. Both were mock-side, but the second is the reason to keep the mock honest:
it only succeeds when the declared shape was actually rendered into the prompt, so a spec the
template forgets to describe fails the mock run instead of silently producing a table a real
model could never have known how to fill.

**Five bugs in the authoring layer itself**, found by scanning it rather than by using it:

1. **Peer modules could not reference each other.** `validate` knew only the built-ins plus
   the module in front of it, so two authored modules naming each other as critics were each
   rejected for naming an unknown module — and neither could be saved first. Authoring a
   *set* of modules is the normal case. Peers now count as known even when quarantined, and
   the cost is named: if every critic a module names is non-runnable, that module effectively
   has no critics at run time, which weakens rule 7. Blocking the author is the worse trade.
2. **`PUT /catalog/{id}` could never save a valid module.** It built its `UserModule` by hand
   instead of merging the shared constitution, so rule 10 fired on every request — four times
   over, once per missing line. There are now one authoring entry point (`catalog.author`) and
   one rule-10 message.
3. **`_check_preset` rejected `with:<authored module>`** with a 400, because it resolved
   through the loader rather than the catalog. Authored modules were unreachable over HTTP
   entirely, while the orchestrator would have run them fine. Same shape as validating inside
   a `StreamingResponse`: a guard has to know as much as the thing it guards.
4. **Retired modules broke replay.** ADR-030 keeps them precisely so old traces stay
   explicable, but `programs()` excluded them, so replaying a card decided by a seven-module
   council failed on a module sitting in the store. Replay and stage re-run now reconstruct
   with `include_retired=True`; new decisions still exclude them.
5. **`--no-persist` hid authored modules.** It swaps in a throwaway store, and reading the
   catalog is a *read* — so the most common authoring move, trying a module without dropping
   a mock card into the corpus, reported `unknown module`.

**A second pass over the vocabulary found four more, and they rhyme with the first five.**
Every one is a rule that *reads* as a guarantee while enforcing nothing, or an error message
that sends the reader to the wrong place:

6. **`covers` pointing at a non-`Table` stage silently approved everything.** Coverage reads
   the covered artifact's `rows`, and only a `Table` has those — every built-in keeps its
   entries under a different key (`people`, `actors`, `options`). So a spec covering a
   `PersonList` stage came back with an empty expected set and passed any table at all. This
   was the quietest failure in the vocabulary and the hardest to notice, because coverage
   reads as the *strongest* rule in a spec. The loader now refuses it.
7. **`sums_to` blamed the total for a non-numeric cell.** `_number(...) or 0.0` swallowed the
   parse failure, so a model writing "about half" produced `'share' sums to 0.500` — sending
   the repair pass to fix arithmetic instead of the cell that is not a number.
8. **The mock could not satisfy a legal spec.** Declaring `distinct` on the same column you
   `covers` is the natural way to write "one row per precedent, no double-counting"; the
   fixup's distinct filler ran *after* the covered value and overwrote it, so coverage failed
   and the blame landed on the author rather than on the mock.
9. **A module id could disagree with its program id.** The catalog keys on `UserModule.id`
   while the engine stamps `ModuleRun.module` from `program.id`. Let those diverge — nothing
   checked — and a preset selects `economist` while the transcript, the calibration scores
   and the extracted memories all say `historian`, with no failure anywhere.

Two smaller ones with the same flavour: `set_module_status` wrote any string it was handed,
because `model_copy(update=...)` does **not** re-validate — a module could sit in a state no
code recognised, with every `status == "active"` check quietly disagreeing with it. And the
store `--no-persist` opens purely to read authored modules from was never closed.

**The pattern worth naming across all eleven.** Almost none of them were logic errors. They
were *guarantees that could not fire* — a rule whose column does not exist, a coverage check
whose prior is the wrong shape, a validator behind a status nothing sets, a route whose guard
knows less than the thing it guards. This is the failure mode a declarative system invites:
the spec is data, so a spec that means nothing still looks like a spec. Hence the loader rules
that reject un-fireable specs, and hence every vocabulary rule being tested in both
directions. A rule that has never been seen to fail is not known to work.

**Sharing is deliberately not part of this.** Importing a stranger's module means executing
their `instruction` text inside a system prompt, which is prompt injection with extra steps.
Authoring your own modules locally has no such exposure, so that ships first; import gets a
review step and its own decision when there is anything to import.

---

## ADR-031 — Check-in reminders ride on the calendar you already have

**Decision.** Cards' `check_on` dates are published as an **iCalendar feed** — a `.ics` file
from `app.cli calendar`, and `GET /calendar.ics`. One VEVENT per unresolved card, with an
alarm, the original question, and the prediction the council made before it knew. No daemon,
no push, no mail.

**Why this was the whole product problem.** Every card is written with a falsifiable
prediction and a check-in date, and until now **nothing ever read that date out loud**. The
CLI nudge printed only if you had already run a command; the nav badge showed only if you had
already opened the app. Both assume you are already there — exactly the assumption that fails
sixty days later. A learning loop nobody is reminded to close does not learn, and that is why
the corpus is empty and four exit criteria are unmeasurable.

**Options weighed.**

- **A background daemon or scheduled task.** Native toasts, immediate. But OS-specific, needs
  an install step, and fails *silently* — a dead scheduler is indistinguishable from "nothing
  due", which is the worst possible failure mode for a reminder.
- **Email through the user's own SMTP.** Free and reaches a phone, but wants an app password
  stored somewhere, and lands in spam often enough to be untrustworthy for something that
  fires twice a month.
- **Web push.** Already rejected in ADR-029: service worker, VAPID keys, a subscription
  store — infrastructure for one user.
- **An iCalendar feed.** Chosen.

**Why the calendar wins on merits, not just on cost.** The reminding infrastructure already
exists, is already installed on the user's phone, and is already checked daily. Building a
notification channel means building delivery, retry, snooze, dismissal and cross-device sync
that a calendar has had for twenty years. It is also the only option that works when the app
is closed, the laptop is shut and the API is down — the exact conditions sixty days after a
decision.

**Given up, and stated plainly.** A subscribed feed only auto-refreshes if the URL is
reachable by the calendar provider's servers, which a localhost API is not. So there are two
modes and the docs say so rather than implying one covers both: `app.cli calendar` writes a
file to import (works offline, is a snapshot, re-import to refresh), and `/calendar.ics` is a
live feed for anyone who exposes the API or points a local client at it.

**The part that is easy to get wrong.** RFC 5545 is unforgiving in ways that fail *silently* —
a calendar handed a malformed file usually drops the event rather than complaining, which
looks exactly like the problem this feature exists to solve. So the builder is tested against
the format rather than trusted, by parsing the document back: CRLF endings; folding at 75
**octets** (not characters — a question with an em-dash is multi-byte, and folding on
character count yields over-length lines some parsers truncate) without ever splitting a
UTF-8 sequence; backslash, semicolon, comma and newline escaped inside TEXT values; `DTSTAMP`
present; all-day events as `VALUE=DATE` with an exclusive `DTEND` on the following day; and a
**stable UID derived from the card id**, which is the difference between a calendar that stays
clean and one the user deletes after the third import.

**Two smaller decisions worth recording.** The alarm fires `-PT9H` — 3pm the day before —
because an all-day event starts at midnight and an alarm "at" the event is a notification in
the middle of the night that is gone by morning. And events are `TRANSP:TRANSPARENT`, because
a check-in is a nudge, not an appointment; marking it busy would make a month of decisions
look like a full calendar.
