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

