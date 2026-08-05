# Specification format

The meta-spec. Every reasoning module — the six built-in ones and every module a
user authors in Phase 5 — is defined by a document that answers the same seven
questions, and by a YAML file the engine can execute.

The prose spec (`docs/agents/<module>.md`) is the design record. The YAML
(`apps/api/app/programs/<module>.yaml`) is the executable form. They must agree;
`tests/test_specs.py` asserts that every stage, artifact and bias in the prose
spec exists in the YAML.

---

## The seven questions

Every module specification must answer these, in this order. If a section cannot
be answered concretely, the module is not ready to build.

| § | Question | Why it is mandatory |
|---|---|---|
| 1 | **Inputs** — what information does this module require, and what does it do when that information is absent? | The failure mode of every reasoning agent is inventing its inputs. A module that needs stakeholder names must *ask* rather than invent a plausible CEO. |
| 2 | **Mental model** — how does it represent the problem internally? | This is the actual differentiator. Two modules with the same representation will converge no matter how different their prompts sound. |
| 3 | **Reasoning stages** — in what order does it think, and what may each stage *not* do? | The executable core. Order is load-bearing: evidence before probability, actors before leverage. |
| 4 | **Artifacts** — what structured outputs must exist before it may conclude? | Enforced by schema. If there is no field for a stance, no stance can be smuggled in early. |
| 5 | **Biases** — what mistakes is it likely to make, and how would an outsider detect each one in its transcript? | A bias without a detector is decoration. Each needs a `watch_for` an *other* module can check. |
| 6 | **Critics** — which modules are best positioned to challenge it, and on what axis? | Critique is routed, not broadcast. The ethicist attacking the analyst's arithmetic is noise. |
| 7 | **Success metrics** — how do we know, months later, whether its advice was good? | Without this, Phase 3 calibration is impossible and confidence stays decorative. |

---

## YAML shape

```yaml
id: strategist                  # module id — the engine's only handle on it
version: 1                      # bump on any stage/artifact change; cards record it
skin:                           # presentation only. Never referenced by the engine.
  name: Alger
  title: The Strategist
  accent: "#b08968"
summary: >
  Maps who actually holds power, what each actor is really optimising for, and
  what leverage exists — then sequences the moves.

# ------------------------------------------------------------------ inputs ---
inputs:
  required:
    - id: actors
      description: Named people or bodies with a stake in the outcome.
      missing_policy: ask       # ask | mark_unknown | infer_labelled | abstain
    - id: decision_options
      description: The concrete choices available.
      missing_policy: mark_unknown
  optional:
    - id: org_context
      description: Reporting lines, company stage, recent changes.

# ------------------------------------------------------------- mental model --
mental_model: |
  A directed graph of actors. Nodes carry formal authority and real influence as
  separate quantities — the gap between them is where most decisions are
  actually decided. Edges are obligations, dependencies and vetoes.

# -------------------------------------------------------------------- stages --
stages:
  - id: map_actors
    name: Enumerate actors
    group: survey               # stages sharing a group may batch into one call
    reads: [context]            # `context` = intake output; else prior stage ids
    produces: ActorList         # must exist in the artifact registry
    instruction: |
      List every actor with a real stake, including the user (id "me") and any
      actor who can block without being consulted.
    must_not:
      - Assess power. This stage only enumerates.
      - Invent named individuals not present in the input. Use role labels.

  - id: graph
    name: Build the stakeholder graph
    group: survey
    reads: [context, map_actors]
    produces: StakeholderGraph
    instruction: |
      For each actor set formal_authority and real_influence independently in
      [0,1]. Add an edge for every obligation, dependency, alliance and veto.
    must_not:
      - Recommend anything.

  # ... remaining stages ...

  - id: recommend
    name: Commit
    group: conclude
    terminal: true              # exactly one terminal stage; only it may
    reads: [graph, leverage, sequence]   # produce a Conclusion
    produces: Conclusion

# --------------------------------------------------------------------- bias --
biases:
  - id: cynicism
    description: Reads malice into what is explained by overload or incompetence.
    watch_for: >
      Attributes a hostile motive to an actor with no evidence of hostility,
      where inattention would explain the same behaviour.
    detectable_by: [psychologist, ethicist]

# ------------------------------------------------------------------ critique --
critique_lens: |
  Attacks power-blindness. Asks who actually signs off, whose consent was
  assumed, and what leverage the other module's plan quietly requires.
critics: [psychologist, ethicist, optimizer, tactician, analyst]  # who challenges THIS module

# ------------------------------------------------------------------- metrics --
success_metrics:
  - id: decider_accuracy
    question: Was the actor named as the real decision-maker the one who decided?
    resolution: user_reported
    horizon_days: 90
  - id: sequence_survival
    question: Did the recommended order of conversations hold?
    resolution: user_reported
    horizon_days: 60

# ---------------------------------------------------------------- behaviour ---
risk_tolerance: 0.55            # 0 = never act without certainty, 1 = act now
time_horizon: medium            # short | medium | long
memory_kind: power_structure    # what this module extracts into memory
voice:
  register: Dry, precise, slightly clinical. Short declaratives.
  forbidden:
    - Fictional references, mysticism, in-world vocabulary.
    - Claiming to be a person, or referring to a fictional biography.
    - Advising deception or fabricated leverage.
domain_weights:                 # synthesis relevance hints; Phase 3 replaces
  negotiation: 1.3              # these with measured accuracy
  business: 1.2
  relationships: 0.7
```

---

## Rules the loader enforces

Violations are load-time errors, not runtime surprises. `programs/loader.py`
raises `ProgramInvalid` and the server refuses to start.

1. **Exactly one `terminal: true` stage**, and it is the last stage.
2. **Only the terminal stage may produce a `Conclusion`.** No other artifact type
   in the registry contains a `stance`-like field, so this is belt and braces.
3. **`reads` must reference `context` or an earlier stage id.** No forward
   references, no cycles — the program is a DAG in declaration order.
4. **Every `produces` must be a registered artifact type** with a Pydantic model
   and an invariant validator.
5. **`group` keys must be contiguous.** A group cannot be interleaved with
   another, because grouped stages become one call.
6. **Every stage needs a non-empty `must_not`.** If a stage has nothing it is
   forbidden from doing, it is not a distinct stage — merge it.
7. **Every bias needs `watch_for` and a non-empty `detectable_by`**, and
   `detectable_by` may not contain the module's own id.
8. **`critics` may not contain the module's own id**, and must be non-empty.
9. **At least two `success_metrics`**, each with a `horizon_days`. A module whose
   advice cannot be scored cannot be trusted with a confidence number.
10. **`voice.forbidden` must inherit the shared constitution** (no fiction, no
    claiming personhood, no deception). The loader merges it in; a spec cannot
    opt out.

---

## What the module never sees

Deliberately withheld from a module's own reasoning stages:

- **Its own `biases`.** Told "you overanalyse", a module performs the absence of
  overanalysis: a shallow answer relabelled as decisiveness. Biases go to the
  critics (with `watch_for`) and to the synthesiser. A weakness only counts if
  someone else can catch it in the transcript. (ADR-003)
- **Other modules' artifacts, during stage 1.** Enforced structurally — the stage
  executor is handed `(program, context, memory)` and there is no parameter
  through which a sibling's output could arrive.
- **Its own `domain_weights`.** Knowing it is considered authoritative here would
  inflate its confidence, which is precisely the number we need uncontaminated.

What it *does* see: the `DecisionContext`, its own prior stage artifacts, and its
`AgentMemory` — recalled items and calibration priors, both attributed and
countable, presented as evidence it may argue with rather than as instructions.

---

## Authoring a new module

The test of a good module is not that it sounds different. It is that it
**changes a recommendation**.

`tests/test_divergence.py` runs a fixed battery of decisions and asserts:

1. **Representation distinctness** — the new module's primary artifact type is
   not already produced by an existing module, or is produced over a materially
   different entity set.
2. **Conclusion divergence** — on ≥2 of the battery decisions, its stance is
   opposed to the current majority.
3. **Critique yield** — it raises critiques that at least one existing module
   accepts in the revision stage.

A module that passes none of these is a voice, not a mind, and is rejected at
review time. This is the bar the Phase 5 marketplace enforces automatically.
