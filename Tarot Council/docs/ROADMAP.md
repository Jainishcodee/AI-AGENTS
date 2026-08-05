# Roadmap

Each phase has an exit criterion. A phase is not done because the code exists; it
is done when the criterion is demonstrably met.

---

## Phase 0 — Specification ✅

Deliberately front-loaded. The reasoning algorithms are the product; discovering
them through prompt iteration would have produced six voices instead of six minds.

- [x] Architecture: the engine as a program interpreter, not a prompt runner
- [x] `SPEC-FORMAT.md` — the seven questions every module must answer, and the
      ten rules the loader enforces
- [x] `ARTIFACTS.md` — artifact registry with machine-checkable invariants
- [x] `COUNCIL.md` — presets, critique routing, synthesis contract, Decision
      Cards, calibration and priors
- [x] Six formal reasoning specifications (`docs/agents/*.md`)
- [x] 18 ADRs, each naming what it gave up

---

## Phase 1 — The engine

### 1a — Interpreter and reasoning core

- [ ] `schemas/` — artifacts, programs, council, trace, cards
- [ ] `engine/invariants/` — one validator per artifact type
      *(probability-tree normalisation, graph connectivity, profile completeness,
      server-side ratio recomputation, premature-stance scan)*
- [ ] `engine/planner.py` — program + depth → execution plan (ADR-013)
- [ ] `engine/executor.py` — stage execution, repair pass, abstention handling
- [ ] `llm/` — Gemini · OpenRouter · Ollama · mock, routed by role
- [ ] `programs/*.yaml` — the six modules, plus the loader's ten rules
- [ ] `programs/presets/*.yaml` — `full`, `strategy`, `people`, `execution`, `life`, `solo:*`
- [ ] `council/` — intake → fan-out → routed critique → revision → synthesis
- [ ] `trace/` — TraceGraph derived from the execution record
- [ ] SSE streaming with typed events; sync endpoint drains the same generator
- [ ] `cli.py` — usable before any UI exists
- [ ] Tests: stage isolation, every invariant, loader rules, full pipeline on mock

**Exit criterion.** `python -m app.cli --provider mock` runs the full pipeline
deterministically and every invariant is exercised by a test. Then, with a real
key: the strategist produces a connected stakeholder graph with a `power_gap` the
user had not considered, and the analyst produces a probability tree whose
arithmetic closes — on a question neither module was tuned against.

### 1b — Web client

- [ ] Next.js + Tailwind, dark, typographic. No LOTM branding anywhere.
- [ ] Live deliberation: six columns, stages filling in as artifacts validate
- [ ] One renderer per artifact type — the graph as a graph, the tree as a tree
- [ ] Thinking Trace: pannable layered map, every node clickable to its artifact
- [ ] Debate view: critiques rendered as edges into the row they target
- [ ] Synthesis: recommendation, disagreements, minority opinions with their
      `when_it_would_be_right`, the veto response, and `council_blind_spot`

**Exit criterion.** A non-technical person asks a real question and, unprompted,
correctly identifies which module they disagree with and why. If they cannot, the
trace has failed regardless of how it looks.

---

## Phase 2 — Memory and continuity

- [ ] Postgres + pgvector; `PostgresStore` replaces `FileStore`
- [ ] Decision Cards persisted with `expected_outcome` and `check_on`
- [ ] Per-module memory extraction — six different rules for what is worth keeping
      (`fact`, `opportunity`, `power_structure`, `emotional`, `workflow`, `promise`)
- [ ] Recall injected into stage 1 as attributed evidence
- [ ] Projects: decisions grouped under an ongoing situation
- [ ] History, search, replay a card against its recorded `program_versions`

**Exit criterion.** A follow-up two weeks later, and the psychologist references
the emotional context of the earlier decision while the analyst references its
facts — each recalling through its own extraction bias, both citing the card.

---

## Phase 3 — Calibration (the defensible phase)

- [ ] Resolution capture: `chose` as free text, `surprises` as a first-class field
- [ ] Per-module Brier scores, per-domain hit rates, execution rates
- [ ] Each module's own `success_metrics` computed from its spec
- [ ] `Prior` generation: `evidence_count ≥ 3`, card-cited, injected as memory
- [ ] Display honesty: nothing shown below n=8; horizon stated beside every number
- [ ] Council health metrics: veto rate, `resolution.chose` outside all proposed
      options (a direct measure of option-generation blindness)

**Exit criterion.** The UI can honestly state, from real recorded outcomes:
*"strategist: 7 of 9 on negotiation decisions, 90-day horizon"* — and the
tactician's prompt contains a prior it argues with.

This is the phase nobody else can copy. The programs are an afternoon's work; the
outcome corpus is not.

---

## Phase 4 — Interface and reach

- [ ] LangGraph migration for cyclic debate and checkpointed resumption
- [ ] Human-in-the-loop: interject mid-deliberation, answer a module's open gap
- [ ] Stage re-run: "re-run the strategist's leverage stage with this new fact"
- [ ] Voice: per-module voices; the council as something you listen to
- [ ] Mobile
- [ ] MCP server: Cognitive OS as a tool other agents can consult

---

## Phase 5 — Marketplace

- [ ] Module builder over `AgentProgram` — stages, artifacts, biases, metrics; no code
- [ ] Automated divergence harness (`SPEC-FORMAT.md` §"Authoring a new module"):
      representation distinctness, conclusion divergence on a fixed battery,
      critique yield. A module that passes none is a voice, not a mind.
- [ ] Sharing, forking, versioning of modules, presets, and whole councils
- [ ] Domain councils: hiring, medical, legal, product

**Exit criterion.** A user-authored module measurably changes the recommendation on
a decision where the built-in six agreed.
