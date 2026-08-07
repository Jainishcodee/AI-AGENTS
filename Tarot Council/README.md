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

**Feedback learning.** Record what actually happened and every module gets scored
against what it said. The grader that judges the outcome is **never shown any
module's confidence** — otherwise calibration measures itself (ADR-021) — and every
number below is computed in Python, never phrased by a model:

```powershell
python -m app.cli cards --status due
python -m app.cli resolve <card-id> --chose "stayed" --outcome "offer came in writing"
python -m app.cli scores
python -m app.cli priors
```

```
module        domain             n    hit   conf   over   brier   exec
strategist    negotiation        9    78%    71%  -0.07   0.151    89%
tactician     negotiation        8    50%    82%  +0.32   0.284    38%
```

Those become **priors** — patterns with counts, citing the cards they came from,
injected into the next run as evidence the module may argue with:

```
tactician   "This user has acted on 3 of your 8 recommendations. Advice they will
             not take has no effect on their life, however sound it is."     n=8
strategist  "On negotiation decisions your reasoning has held up well for this
             user: right in 78% of 9 tested cases."                         n=9
```

Nothing here rewrites a program — a system that tunes its own prompts from its own
scoring drifts, and then you can no longer tell whether the module improved or the
yardstick moved.

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

**1. The reasoning core**

```powershell
cd "apps/api"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\..\.env.example ..\..\.env     # paste your free GEMINI_API_KEY

# the whole pipeline against a deterministic fake model — no key, no network
python -m app.cli --provider mock "Should I quit my internship?"

# for real
python -m app.cli --preset strategy --depth quick "Should I quit my internship?"

pytest                                  # 143 tests, ~2s
uvicorn app.main:app --reload --port 8787
```

**2. The web client**

```powershell
cd "apps/web"
npm install
npm run dev                             # http://localhost:3000
```

The browser never talks to the API directly — everything goes through
`app/api/council/[...path]`, so there is no CORS to configure and no API URL in the
client bundle. To drive the UI without spending quota, start the API with every role
pointed at the mock provider:

```powershell
$env:COUNCIL_MODEL_INTAKE="mock:m"; $env:COUNCIL_MODEL_REASONING="mock:m"
$env:COUNCIL_MODEL_SYNTHESIS="mock:m"; uvicorn app.main:app --port 8787
```

**3. As a tool for other agents (MCP)**

```powershell
python -m app.mcp                    # JSON-RPC over stdio
python -m app.mcp --provider mock    # no key, no network
```

Six tools: `consult`, `list_modules`, `get_deliberation`, `record_outcome`,
`track_record`, `pending_checkins`. `consult` returns the recommendation *and* the
dissent — disagreements, minority opinions, and what no module examined — plus a
`deliberation_id` for the full transcript, so a calling agent gets something it can act
on without swallowing 40k tokens.

**Re-running without rewriting history**

```powershell
python -m app.cli rerun <deliberation-id> --module strategist --from-stage leverage `
    --fact "The investor said in writing the title is a non-event"
python -m app.cli refine <deliberation-id> --answer "Savings are six months, not four"
```

Because every stage is a separately validated artifact, re-running one module from one
stage carries every earlier artifact untouched. Both commands produce a *new*
deliberation with `derived_from` set — the original is immutable, because it is what
the Decision Card gets scored against (ADR-022).

Presets: `full` · `strategy` · `people` · `execution` · `life` · `solo:<module>`.
Depths: `quick` (~9 calls) · `standard` (~26) · `deep` (~56).

> **On free-tier quota.** Gemini's free tier meters *requests per minute* — around 5
> to 10 depending on the model, and `gemini-2.5-pro` is not on it at all. The
> per-minute cap, not model quality, is what decides whether a run finishes: a
> `standard` full-council deliberation is ~26 calls and takes minutes of wall clock.
> Start with `--preset solo:<module> --depth quick` (~4 calls) while iterating. See
> ADR-020.

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
