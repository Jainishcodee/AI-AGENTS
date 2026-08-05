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

