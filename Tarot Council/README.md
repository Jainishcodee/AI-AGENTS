# Cognitive OS

*Repository codename: Tarot Council.*

Six **thinking engines**, not six chatbots. Each one executes a different
reasoning algorithm over the same decision, produces the artifacts that algorithm
demands, attacks the others' reasoning, revises its confidence, and a synthesiser
commits to one recommendation with the dissent left intact.

The difference from every multi-agent demo is that an agent here is **a program the
runtime executes stage by stage**, not a personality with a prompt:

```
question
   │
   ▼  TACTICIAN                                     artifact produced
      read_situation ─────────────────────────────►  SituationRead
      generate       ─────────────────────────────►  OptionSet   (≥7, quota-enforced)
      asymmetry      ─────────────────────────────►  AsymmetryTable
      rank           ─────────────────────────────►  RankedOptions
      unexpected     ─────────────────────────────►  UnexpectedMove
      reactions      ─────────────────────────────►  ReactionForecast
      commit         ─────────────────────────────►  Conclusion  ◄─ the only stage
                                                                    that may hold
                                                                    a stance
```

Every arrow is a real execution boundary. Every box is a validated artifact
persisted in the trace. The stakeholder graph must be connected and contain a `me`
node. The probability tree's sibling branches must sum to 1.0. The psychologist's
profile set must cover every person named, all nine fields, every time. These are
checked in code — instructions are advisory, validators are not.

## The six modules

| module | skin | algorithm | forced artifacts |
|---|---|---|---|
| `analyst` | Klein | evidence before conclusion | evidence ledger → gaps → base rates → **probability tree** → pre-mortem |
| `tactician` | Lumian | action under uncertainty | situation read → **≥7 options** → asymmetry → rank → unexpected move → reaction forecast |
| `strategist` | Alger | power and incentives | actors → **stakeholder graph** → incentives → leverage → hidden dynamics → sequence |
| `psychologist` | Audrey | human psychology | cast → **9-dimension profile per person** → self-read → dynamics → scripts → cost |
| `optimizer` | Fors | constraint and efficiency | outcome → waste audit → **one binding constraint** → simplest path → effort/return → system |
| `ethicist` | Leonard | values and regret | parties → value audit (quoted) → harm ledger → **regret at 1/5/10y** → integrity → inaction cost |

Modules are the engine's only handle; skins are presentation. Planned modules with
no skin at all: `economist`, `lawyer`, `historian`, `adversary`, `planner`.

## What makes it compound

**The Thinking Trace.** A public reasoning map — question → context → six parallel
columns of artifacts → the critique mesh between them → conflicts → consensus →
recommendation. It is *derived* from the execution record, never generated, so the
map cannot disagree with the territory.

**Decision Cards.** Every deliberation persists with a falsifiable
`expected_outcome` and a `check_on` date written *at deliberation time*. Later you
record what actually happened.

**Feedback learning.** From resolved cards: per-module Brier scores, per-domain hit
rates, and natural-language priors with evidence counts fed back into future
reasoning —

```
strategist  "In 4 of 6 resolved career decisions, the actor who actually blocked
             was one you had not mentioned."                     n=6
tactician   "Bold moves: 8 proposed, 3 taken, 2 worked. All 5 declined were
             tagged one_way."                                    n=8
```

The six programs are copyable in an afternoon. Four hundred resolved Decision Cards
belonging to one person are not.

## Status

**Phase 1 — specification complete, engine in progress.** See
[docs/ROADMAP.md](docs/ROADMAP.md).

## Documentation

Read in this order:

| doc | what it settles |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | the engine, the pipeline, module boundaries, data model |
| [SPEC-FORMAT.md](docs/SPEC-FORMAT.md) | the meta-spec: the seven questions every module must answer |
| [ARTIFACTS.md](docs/ARTIFACTS.md) | the artifact registry and every machine-checked invariant |
| [COUNCIL.md](docs/COUNCIL.md) | presets, critique routing, synthesis contract, Decision Cards, calibration |
| [DECISIONS.md](docs/DECISIONS.md) | 18 ADRs, including what each one gave up |
| `docs/agents/*.md` | the six formal reasoning specifications |

## Quick start

```powershell
cd "apps/api"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\..\.env.example ..\..\.env     # paste your free GEMINI_API_KEY

# full pipeline against a deterministic fake model — no key, no network
python -m app.cli --provider mock "Should I quit my internship?"

# for real
python -m app.cli --preset strategy --depth standard "Should I quit my internship?"

# server
uvicorn app.main:app --reload --port 8787     # http://127.0.0.1:8787/docs
```

Presets: `full` · `strategy` · `people` · `execution` · `life` · `solo:<module>`.
Depths: `quick` (~9 calls) · `standard` (~26) · `deep` (~56).

## Layout

```
apps/api/app/
  core/       config, logging, errors
  schemas/    the wire contract — artifacts, programs, council, trace, cards
  llm/        provider abstraction (Gemini · OpenRouter · Ollama · mock)
  engine/     the interpreter: planner, stage executor, invariant validators
  programs/   the six modules as YAML + presets. Data, not behaviour.
  prompts/    Jinja templates
  council/    orchestrator: intake → fan-out → critique → revise → synthesise
  trace/      TraceGraph construction. Pure functions.
  memory/     MemoryStore protocol, per-module extraction, calibration
  api/        FastAPI routers
apps/web/     Next.js client (Phase 1b)
docs/
```

`engine/` must never import `programs/` — the moment it does, it stops being an
interpreter and becomes a hardcoded pipeline.

## Licence

Private, unreleased.
