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

Phases 1–4 built; Phase 5 authoring built with its exit criterion **unmeasured**; Phase 6
in progress. Reasoning engine, web client, SQLite persistence, projects, the calibration
loop, replay/backtesting, stage re-run, mid-deliberation interjection, resumable
deliberations, a spoken briefing, an MCP server, a divergence harness, user-authored modules,
and calendar-delivered check-ins, with sharing, forking and prompt-surface review of authored modules. 496 tests.

Four exit criteria are unmet and share one cause — nobody has yet used this on real decisions
over real time, so the corpus is empty. They are tabulated at the top of
[docs/ROADMAP.md](docs/ROADMAP.md), which says what each phase claims and — more usefully —
what it does not. Closing that gap is what Phase 6 is for.

## Documentation

Read in this order:

| doc | what it settles |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | the engine, the pipeline, module boundaries, data model |
| [SPEC-FORMAT.md](docs/SPEC-FORMAT.md) | the meta-spec: the seven questions every module must answer |
| [ARTIFACTS.md](docs/ARTIFACTS.md) | the artifact registry and every machine-checked invariant |
| [COUNCIL.md](docs/COUNCIL.md) | presets, critique routing, synthesis contract, Decision Cards, calibration |
| [DECISIONS.md](docs/DECISIONS.md) | 32 ADRs, including what each one gave up |
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

pytest                                  # 496 tests, ~7s
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

**Answering an unknown while it is still thinking**

```
POST /council/live/{run_id}/inject   {"facts": ["The offer arrived in writing"]}
```

A run is addressable from its first event, so you can answer a gap the moment a module
raises it. Every batch that has not started picks the fact up; batches in flight are
left alone, so a stage's output is always explicable by the context it was handed. Late
facts are labelled as late rather than merged silently.

**Is it actually six minds, or six voices?**

```powershell
python -m app.cli divergence          # spec-level checks, instant
python -m app.cli divergence --live   # runs the decision battery; costs real calls
```

The claim is falsifiable, so it is measured rather than asserted (ADR-026). The structural
half checks that every module owns an artifact type nothing else produces — two modules
with the same representation converge however differently they are phrased. The live half
runs an eight-decision battery and measures dissent rate, critique yield, and word overlap
between stances.

The part worth trusting: the harness **fails the mock council**, whose six modules really
are one voice, at 1.00 stance overlap. An instrument only ever pointed at a passing case
is not known to detect anything.

**Grouping a chain of decisions, and backtesting the council**

```powershell
python -m app.cli projects --new "Leaving the internship"
python -m app.cli ask --project <id> "Should I ask for the offer in writing?"
python -m app.cli replay <card-id>
```

Decisions in a project share memories, so an unrelated side project stops bleeding into a
salary conversation. `replay` re-decides a *resolved* card against today's programs and
grades it against what actually happened — the resolved corpus as a test set for the
council itself. Memories and priors derived from that card are withheld for the run, and
the count is reported, because otherwise a module scores well by reading its own answer
(ADR-025).

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

**Picking a deliberation back up**

```powershell
python -m app.cli resume                # lists what is resumable, with what it got through
python -m app.cli resume <id>
```

On a free tier a deliberation can outlive its quota window. When a provider fails, every
completed module run and every partial one is checkpointed, and resuming restarts each
module at the first stage it had not finished — nothing already answered is paid for twice.
The same mechanism covers a closed laptop. A provider outage is now distinguishable from a
module choosing to abstain, which it previously was not: an exhausted quota used to produce
a "complete" deliberation with six empty runs and file it in the corpus (ADR-027).

**Listening to it instead of reading it**

```powershell
python -m app.cli brief <deliberation-id>            # the script
python -m app.cli brief <deliberation-id> --speak    # needs: pip install edge-tts
```

About ninety seconds: the recommendation, what would make it wrong, then each dissenting
module in its own voice saying what it would do instead and when it would be right. Not the
transcript read aloud — stakeholder graphs and cited rows do not survive being spoken, and
twenty minutes of audio is worse than none (ADR-028). `edge-tts` is free and optional; the
script is produced either way.

Presets: `full` · `strategy` · `people` · `execution` · `life` · `solo:<module>`.
Depths: `quick` (~9 calls) · `standard` (~26) · `deep` (~56).

**Authoring a seventh module**

```powershell
python -m app.cli modules                                       # built-in and authored
python -m app.cli modules --load scripts/example-module.yaml     # validate and save
python -m app.cli modules --activate historian
python -m app.cli --preset with:historian "Should I take the smaller offer?"
```

A module is an `AgentProgram` in the same YAML the built-in six are written in, so the way
to author one is to copy `app/programs/analyst.yaml` and edit it. It is held to the **same
ten rules**, including the one that matters most: every stage's `produces` must name an
artifact type with a machine-checkable invariant, which is what stops an authored module
being a persona with a prompt (ADR-012).

You get there by declaring the artifact's shape rather than writing Python:

```yaml
  - id: precedents
    produces: Table
    table:
      columns: [precedent, mechanism, outcome_rate, applicability]
      min_rows: 3                              # a "rate" over two cases is a story
      required: [precedent, mechanism]         # non-empty in every row
      distinct: [precedent]                    # no double-counting the same case
      required_tags: [ended_well, ended_badly] # forbid a one-sided reference class
      ranges: [{column: outcome_rate, minimum: 0.0, maximum: 1.0}]

  - id: divergence
    produces: Table
    group: differentiate                       # a different group, on purpose
    table:
      columns: [precedent, difference, weakens_or_strengthens]
      covers: {stage: precedents, column: precedent}   # every precedent, no omissions
```

These are checked in code, in the same pass as the probability tree and the stakeholder
graph. `covers` reaches across a stage boundary, which is what makes a multi-stage authored
module more than a sequence of unrelated prompts — and it must point at a *different* group,
because grouped stages become one call and the covered artifact would not exist yet.

The vocabulary was extracted, not invented: every rule is a shape the built-in validators
already assert, and the test suite proves it by restating `OptionSet`'s real invariant
declaratively. What it cannot express — recursive structures, cross-field semantics — stays
hand-written, so an authored module is held to a real but weaker standard than the six
(ADR-030).

**Sharing, forking and reviewing**

```powershell
python -m app.cli modules --fork analyst --as my_analyst      # copy a built-in, keep lineage
python -m app.cli modules --export my_analyst --out mine.yaml # a module IS a file
python -m app.cli modules --review my_analyst                 # what it injects into prompts
```

Sharing is a file: export writes the same YAML a module is authored in, and the round trip
is pinned by tests for every built-in. A fork records `based_on` and always lands as a
draft — nobody has read the copy yet. Before activating a module you did not write, run
`--review`: it prints every prose string the module injects into prompts, with the two
channels a reviewer would miss called out loudly (`watch_for` renders into *other* modules'
critique prompts, and `voice.forbidden` reads as safety text while being arbitrary
instruction). The trust boundary is activation; review is the tool that informs it, not a
gate to cargo-cult (ADR-032). Edits that change a program auto-bump its `version`, because
deliberations pin `program_versions` and replay compares then-vs-now.

A module that breaks a rule is **saved and quarantined**, not rejected: it is listed with its
full error list and cannot run until it validates and you activate it. Built-ins still fail
loudly — a malformed built-in refuses to let the server start — because that is a developer
error, whereas a half-finished draft is the normal state of authoring and a draft you cannot
save is a draft you cannot fix (ADR-030).

The engine has no idea any of this exists. An authored module executes through the same
`run_program` with no new code path, which is what ADR-011's "an agent is a program" was for.

**Closing the loop — the half that actually makes it yours**

```powershell
python -m app.cli checkin       # walks every due card, three questions each
python -m app.cli calendar      # writes an .ics of every open check-in
```

Every card is written with a falsifiable prediction and a check-in date, and until Phase 6
**nothing ever read that date out loud** — the nudge printed only if you had already run a
command, and the badge showed only if you had already opened the app. Both assume you are
already there, which is the assumption that fails sixty days later.

So the reminder rides on the calendar you already check: import the `.ics` once, or subscribe
to `/calendar.ics` if the API is reachable. Each event carries the original question and what
the council predicted before it knew, so the check-in takes thirty seconds instead of
requiring you to reconstruct the decision (ADR-031).

`checkin` then asks three questions per card and grades every module against what it said.
Nothing in the system learns anything until that happens.

**Storage.** SQLite by default — one file under `apps/api/var/`, no service, FTS5 with
BM25 for recall (ADR-024). Coming from an earlier JSON-file build:
`python -m app.cli migrate` (idempotent).

> **On free-tier quota.** Gemini's free tier meters *requests per minute* — around 5
> to 10 depending on the model, and `gemini-2.5-pro` is not on it at all. The
> per-minute cap, not model quality, is what decides whether a run finishes: a
> `standard` full-council deliberation is ~26 calls and takes minutes of wall clock.
> Start with `--preset solo:<module> --depth quick` (~4 calls) while iterating. See
> ADR-020. If a run does hit the wall, nothing is lost — it checkpoints, and
> `python -m app.cli resume` picks it up without re-paying for a single completed stage.

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
  learning/   grader (blind) · scoring (pure maths) · priors (templated counts)
  memory/     SQLiteStore (default) · FileStore (legacy) · InMemoryStore (tests)
  mcp/        JSON-RPC over stdio — the council as a tool for other agents
  api/        FastAPI routers
apps/web/     Next.js client (Phase 1b)
docs/
```

`engine/` must never import `programs/` — the moment it does, it stops being an
interpreter and becomes a hardcoded pipeline.

## Licence

Private, unreleased.
