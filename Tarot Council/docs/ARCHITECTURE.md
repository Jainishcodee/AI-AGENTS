# Architecture — Cognitive OS

> Codename of this repository: *Tarot Council*. Product name: **Cognitive OS**.
> The LOTM characters are a **skin**. The engine only ever references modules.

## 1. What this is

Not six AIs answering a question. **Six thinking engines executing six different
algorithms over the same input.**

The distinction is the whole product. Consider "should I leave my job?"

**The boring version** — the one almost every multi-agent demo ships:

```
question ──► agent prompt ──► answer
```

Six of those in parallel gives you one answer in six voices, because the model's
prior about the sensible answer is far stronger than a tone instruction.

**What we build instead** — the agent *is a program*, and the runtime executes it
stage by stage:

```
question
   │
   ▼  ┌─────────────────────────────────────────────────────────────┐
      │ TACTICIAN (skin: Lumian)                                    │
      │                                                             │
      │ read_situation → SituationRead                              │
      │        │  what game is being played · who thinks it's       │
      │        │  a different game · information asymmetries        │
      │        ▼                                                    │
      │ generate      → OptionSet        (≥7, quota-enforced)       │
      │        ▼                                                    │
      │ asymmetry     → AsymmetryTable   (downside · upside · ratio)│
      │        ▼                                                    │
      │ rank          → RankedOptions                               │
      │        ▼                                                    │
      │ unexpected    → UnexpectedMove                              │
      │        ▼                                                    │
      │ reactions     → ReactionForecast (2 moves deep)             │
      │        ▼                                                    │
      │ commit        → Conclusion       ◄── only stage that may    │
      └────────────────────────────────────────hold a stance────────┘
```

Each arrow is a real execution boundary. Each box is a validated artifact
persisted in the trace. `generate` cannot see `commit`'s schema; `read_situation`
has no field in which a recommendation could be written.

That is the difference between a personality and an algorithm.

## 2. The engine is the product

There is no `class KleinAgent`. There is one **cognitive engine** that executes
any `AgentProgram`:

```python
async def execute(program: AgentProgram, ctx: DecisionContext) -> AgentRun:
    scratch: dict[StageId, Artifact] = {}
    for group in plan(program, depth):          # batching, see §6
        inputs = {sid: scratch[sid] for sid in group.reads}
        artifact = await run_stage(group, ctx, inputs)   # LLM call + validate
        validate_invariants(artifact)                    # code, not prompt
        scratch[group.produces] = artifact
        yield StageComplete(...)
    return AgentRun(program.id, scratch, trace_nodes, usage)
```

Everything specific to Klein or Alger lives in data. The engine is ~300 lines and
never mentions an agent by name. Consequences:

- A new module is a YAML file. Phase 5's marketplace is the same code path.
- Every stage of every agent is independently inspectable, cacheable, and
  re-runnable. "Re-run Alger's leverage stage with this new fact" is a supported
  operation, not a rebuild.
- The Thinking Trace (§7) is a byproduct of execution rather than a feature.

## 3. Artifacts are typed, and invariants are checked in code

An artifact is not "structured output". It is a named type with machine-checkable
invariants. This is where rigor actually comes from — instructions are advisory,
validators are not.

| Artifact | Owner | Invariants enforced in code |
|---|---|---|
| `EvidenceLedger` | analyst | every row has `status ∈ {given, inferred, assumed, speculative, unknown}`; ≥1 row marked `load_bearing`; no row may contain a recommendation verb |
| `ProbabilityTree` | analyst | sibling branch probabilities sum to 1.0 ± 0.02; depth ≥ 2; every leaf has an outcome |
| `StakeholderGraph` | strategist | contains a node with `id == "me"`; graph is connected; every edge endpoint exists; `formal_authority` and `real_influence` ∈ [0,1] |
| `PersonProfileSet` | psychologist | one complete profile per person named in `cast`, all 9 fields present — **no partial profiles** |
| `AsymmetryTable` | tactician | every option from `OptionSet` appears exactly once; `reversibility ∈ {reversible, costly, one_way}` |
| `EffortReturnRanking` | optimizer | must include the `do_nothing` baseline row |
| `HarmLedger` | ethicist | every option scored; `who_pays` non-empty for every non-zero harm |
| `Conclusion` | all | `confidence.falsifier` non-empty; `stance` is imperative and names a first action |

A validation failure triggers one repair call showing the model the validator's
complaint. A second failure records the agent as an abstention rather than
silently accepting a malformed artifact. See [ARTIFACTS.md](ARTIFACTS.md) for the
full registry and [SPEC-FORMAT.md](SPEC-FORMAT.md) for how a program declares
them.

**The structural guarantee:** only the terminal stage of a program produces a
`Conclusion`. No earlier artifact schema contains a `stance`, `recommendation`,
or `advice` field. Klein *cannot* advise before producing evidence, because there
is nowhere to put the advice.

## 4. Modules, not characters

Every program declares a `module` and a `skin`. The engine, the trace, the
calibration tables, and the synthesiser reference only `module`.

| module | skin (v1) | eventual public name |
|---|---|---|
| `analyst` | Klein | Analyst |
| `tactician` | Lumian | Tactician |
| `strategist` | Alger | Strategist / Negotiator |
| `psychologist` | Audrey | Psychologist |
| `optimizer` | Fors | Systems Engineer |
| `ethicist` | Leonard | Counsel |

Planned modules with no LOTM skin at all: `economist`, `lawyer`, `historian`,
`adversary` (red-team the council's own recommendation), `planner` (long-horizon).
The skin layer is presentation config — a `skin_pack` the UI applies. Dropping
LOTM is deleting one file.

## 5. Pipeline

```
                         ┌──────────────┐
   question ───────────►  │  0  Intake   │  cheap model · 1 call
                         └──────┬───────┘  DecisionContext: options, actors,
                                │          constraints, time box, domain,
                                │          reversibility, stated values
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
  ┌───────────┐           ┌───────────┐           ┌───────────┐
  │ analyst   │           │ tactician │    …      │ ethicist  │   6 programs,
  │ 7 stages  │           │ 7 stages  │           │ 7 stages  │   fully isolated
  └─────┬─────┘           └─────┬─────┘           └─────┬─────┘
        └───────────────────────┼───────────────────────┘
                                ▼
                         ┌──────────────┐   each module sees the others'
                         │ 2  Critique  │   artifacts + their blind-spot
                         └──────┬───────┘   detectors. Targets claim/row ids.
                                ▼
                         ┌──────────────┐   accept / reject each critique with
                         │ 3  Revise    │   grounds. Confidence updated.
                         └──────┬───────┘
                                ▼
                         ┌──────────────┐   strongest model. Reads every
                         │ 4 Synthesis  │   artifact, every rejected critique,
                         └──────┬───────┘   every falsifier, and the user's
                                ▼           calibration history.
                        ┌───────────────┐
                        │ Decision Card │  persisted · revisitable · scoreable
                        └───────────────┘
```

Stage-1 independence is **structural**: an agent run is constructed from
`(AgentProgram, DecisionContext, AgentMemory)` only. There is no parameter through
which another agent's output could arrive. Tests assert it by inspecting rendered
prompts for the other agents' distinctive strings.

## 6. Execution granularity — how we afford this

Naively: 6 modules × 7 stages = 42 calls, plus critique, revision and synthesis
≈ 55 calls per question. Too slow and too expensive to be the only mode.

The program is the same at every depth; only the **plan** changes. Each stage
declares a `group` key, and contiguous stages sharing a group may be executed in
one call:

| depth | plan | calls | latency | use |
|---|---|---|---|---|
| `quick` | all stages of a program in 1–2 calls, artifacts still individually validated | ~9 | ~15 s | first look |
| `standard` | one call per `group` (≈3 per module) + critique + revise + synthesis | ~26 | ~50 s | default |
| `deep` | one call per stage, two critique rounds | ~56 | ~3 min | irreversible decisions |

This is the key affordance of separating program from plan: rigor is preserved at
every depth because *validation is per-artifact regardless of how many artifacts
came back in one response*. Only the amount of independent deliberation per stage
changes. Nothing about the algorithm is skipped at `quick` — the tree still gets
built, it just gets built in the same breath as the ledger.

## 7. The Thinking Trace

Not chain-of-thought. Not a log. A **public reasoning map** the user can read and
navigate — the artifact-level structure of how the council got there.

It is derived. The engine already knows every stage, its declared `reads`, and its
produced artifact, so the graph is free:

```python
TraceGraph
  nodes: [ TraceNode(id, kind, module, stage_id, label, artifact_ref, status) ]
  edges: [ TraceEdge(src, dst, kind, label) ]

TraceNode.kind  = question | context | stage_artifact | conclusion
                | critique | revision | conflict | consensus | recommendation
TraceEdge.kind  = derives_from    stage read dependency, from the program
                | critiques       module A's critique → the row it targets
                | revises         revision → the critique it accepted
                | conflicts_with  two conclusions the synthesiser marked opposed
                | supports        artifact row → synthesis consensus point
```

Rendered as a left-to-right layered graph: question → context → six parallel
columns of stage artifacts → the critique mesh between them → conflicts →
consensus → recommendation. Excalidraw-flavoured, pannable, every node clickable
down to the artifact that produced it.

Two properties matter more than the visuals:

- **Nothing in the trace is generated for the trace.** Every node references a
  real validated artifact. A pretty reasoning diagram that an LLM wrote *about*
  its reasoning is theatre; this is the execution record.
- **Layout is computed client-side from `derives_from` depth.** No LLM decides
  where boxes go, so the same deliberation always renders identically.

## 8. Decision Cards and feedback learning

This is the moat. Anyone can copy the six modules. Nobody can copy your outcome
history.

A deliberation persists as a **Decision Card**:

```python
DecisionCard
  question, context, trace_id, created_at
  recommendation          what the council committed to
  per_module_stance       { module: (stance, confidence, falsifier) }
  expected_outcome        falsifiable, with a check_on date
  minority_opinions       [ { module, position, when_it_would_be_right } ]
  # filled in later, by the user:
  resolution              { chose_what, actual_outcome, happened_at, notes }
  scoring                 { module: Verdict(right | wrong | partial | untested) }
```

`expected_outcome` must be falsifiable and dated at write time — that is what
makes scoring possible at all. The card schedules its own check-in.

From resolved cards we compute, per module **per user**:

- **Brier score** on stated confidences → real calibration, not claimed
- **Domain accuracy** — the strategist may be 89% on negotiation and 40% on money
- **Learned priors** — patterns with evidence counts, fed back into stage 1:

```
strategist → "In 6 of 8 resolved career decisions, this user underestimated
             how much of the outcome was decided by one person's opinion."
tactician  → "Bold moves recommended to this user: 8 taken, 5 worked (63%).
             The two that failed both involved an unstated financial floor."
```

Injected as `AgentMemory.priors` into the reasoning stages, attributed and
countable. This is why per-agent memory is six stores with six extraction rules
rather than one shared index — the analyst remembers facts, the psychologist
remembers emotional history, the ethicist remembers promises.

An agent whose prior is contradicted by the current context must say so. Priors
are evidence, not instructions.

## 9. Module boundaries

```
apps/api/app/
  core/         config, logging, errors. Imports nothing from the app.
  schemas/      the wire contract. artifacts/ · programs/ · council/ · trace/ · cards/
  llm/          provider abstraction + JSON contract enforcement. Knows nothing
                about councils, agents, or artifacts.
  engine/       the cognitive engine: planner, stage executor, invariant
                validators, artifact registry. Knows nothing about which agents
                exist — it executes whatever program it is handed.
  programs/     the six AgentPrograms as YAML + loader. Data, not behaviour.
  prompts/      Jinja templates + renderer. (program, stage, context) → string.
  council/      orchestrator: intake, fan-out, critique, revision, synthesis.
                The only module that knows what a deliberation is.
  trace/        TraceGraph construction from AgentRun records. Pure functions.
  learning/     grader (one blind LLM call) · scoring (pure arithmetic) · priors
                (templated from real counts). See ADR-021.
  memory/       MemoryStore protocol and implementations. Delegates computed views
                — priors, scores — to learning/.
  api/          FastAPI routers. Thin: validate, call council, stream events.
  mcp/          JSON-RPC over stdio, stdlib only. Six tools, summarised for agents
                rather than mirroring the HTTP surface.
  cli.py        terminal client: ask · cards · resolve · grade · scores · priors ·
                memories · rerun · refine.
```

Dependencies point one way:
`api → council → {engine, programs, prompts, memory, trace, learning} → llm →
schemas → core`, with `memory → learning` for the computed views.

The two boundaries worth defending: **`engine/` must never import `programs/`**
(it would stop being an interpreter and become a hardcoded pipeline), and
**`llm/` must never import `schemas/artifacts`** (it is the module most likely to
be extracted into a shared package).

## 10. Streaming and the event contract

A `standard` deliberation takes ~50 s. Blocking on that wastes the best part of
the product: watching six algorithms visibly execute, stage by stage, and then
turn on each other. Events (`council/events.py`):

```
stage_started       { phase, label }
intake_complete     { context }
module_started      { module }
artifact_complete   { module, stage_id, artifact }   ← the trace grows live
artifact_invalid    { module, stage_id, error, repairing }
module_complete     { module, conclusion }
module_abstained    { module, reason }               ← never fails the council
critique_complete   { module, critiques[] }
revision_complete   { module, revision }
trace_updated       { nodes[], edges[] }             ← incremental
synthesis_complete  { synthesis }
card_created        { card_id, check_on }
done                { usage, cost_estimate }
```

`POST /council/deliberate` streams these; `/deliberate/sync` drains the same
generator. One code path, so streamed and non-streamed results cannot drift.

## 11. Data model (Phase 2 target)

```sql
decision_cards    id, user_id, project_id, question, domain, depth, created_at,
                  context jsonb, recommendation jsonb, expected_outcome jsonb,
                  check_on date, resolution jsonb, usage jsonb
agent_runs        id, card_id, module, program_version, artifacts jsonb,
                  conclusion jsonb, usage jsonb, abstained bool
trace_graphs      card_id, nodes jsonb, edges jsonb
module_scores     user_id, module, domain, n, brier, hit_rate, updated_at
module_priors     id, user_id, module, pattern, evidence_count, confidence,
                  derived_from uuid[], embedding vector(768)
programs          id, version, module, skin, spec jsonb, author_id, published
```

`programs` being a table rather than only files is what makes Phase 5 possible:
a user-authored module is a row, and `agent_runs.program_version` means an old
Decision Card can always be replayed against the exact program that produced it.

## 12. Deliberately not yet

- **LangGraph.** The engine is a plain async state machine over an explicit state
  object. It is already a graph interpreter — adopting LangGraph buys
  checkpointing and cyclic debate, which is Phase 4. Doing it now adds
  indirection over exactly the code we will iterate on most.
- **Auth.** `user_id` is in every schema and is currently a constant. The column
  is the expensive retrofit; the login flow is not.
- **A vector DB.** pgvector on the Postgres we already need, until recall quality
  is measurably the bottleneck.
