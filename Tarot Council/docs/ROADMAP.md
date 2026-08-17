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

### 1a — Interpreter and reasoning core ✅

- [x] `schemas/` — 37 artifact types, programs, council, trace, cards, events
- [x] `engine/invariants.py` — validators + server-side normalizers
      *(probability-tree normalisation, graph connectivity, profile completeness,
      ratio recomputation, `power_gap` tagging, premature-stance scan, citation
      resolution, confidence ceiling over admitted assumptions)*
- [x] `engine/planner.py` — program + depth → execution plan (ADR-013)
- [x] `engine/executor.py` — stage execution, repair pass, abstention handling
- [x] `llm/` — Gemini · OpenRouter · Ollama · mock, routed by role, RPM-paced
- [x] `programs/*.yaml` — the six modules, plus the loader's ten rules
- [x] `programs/presets.yaml` — `full`, `strategy`, `people`, `execution`, `life`, `solo:*`
- [x] `council/` — intake → fan-out → routed critique → revision → synthesis
- [x] `trace/` — TraceGraph derived from the execution record
- [x] SSE streaming with typed events; sync endpoint drains the same generator
- [x] `cli.py` — usable before any UI exists
- [x] 143 tests: stage isolation, every invariant, loader rules, planner at all
      depths, prose-spec↔YAML agreement, full pipeline on mock

**Exit criterion — met.** `python -m app.cli --provider mock` runs the full
pipeline deterministically: 42 artifacts across six modules, 27 routed critiques,
six revisions, synthesis, trace and Decision Card, in under two seconds with no
key and no network. Every invariant is exercised in both directions by a test.

Against a real free-tier Gemini key, on questions no module was tuned against: the
strategist produced a connected stakeholder graph with authority and influence
scored separately and cited its own graph nodes in its conclusion; the citation
invariant caught two invented row references and the repair pass fixed them; and
when the strategist hit a quota wall mid-program it was recorded as an abstention
without taking the council down.

Deferred from 1a, deliberately: `Prior` generation has no source of resolved cards
until Phase 3, so `InMemoryStore.priors()` returns an empty list rather than
inventing plausible priors — which would poison the exact mechanism it exists to
serve (ADR-018).

### 1b — Web client

- [x] Next.js 15 + Tailwind v4, dark, typographic. No LOTM branding anywhere.
- [x] Same-origin proxy (`app/api/council/[...path]`) — no CORS on the streaming
      POST, no API URL in the client bundle, one place for Phase 2 auth
- [x] SSE-over-POST by hand (`EventSource` cannot POST) + a reducer over the typed
      event stream; no state library, because the backend already emits the machine
- [x] Live deliberation: module columns with a stage rail that fills as artifacts
      validate, and shows which stages needed a repair
- [x] A renderer per artifact type, registry-dispatched with a generic fallback —
      the stakeholder graph as an authority-vs-influence scatter, the probability
      tree as a tree with running joint probabilities, the nine dimensions as a
      person-by-dimension matrix
- [x] Debate view grouped by target, each critique showing the artifact row it
      attacks, with `strong_agreement` rendered as agreement rather than as attack
- [x] Synthesis: recommendation, unresolved disagreements, biases that fired,
      `council_blind_spot` above the fold, minority opinions with their
      `when_it_would_be_right`, the veto response, and the dated bet on record
- [x] Thinking Trace: deterministic layered map from server-computed depth,
      pan/zoom, click to isolate a node and its neighbours
- [x] App shell with routes — the single-screen version made the product look like
      something you ask once, when the whole argument is that it accumulates
- [x] Interjection control: the unknowns the council raised, with an input to answer
      them mid-run and a note saying which modules already finished
- [x] Density fix — module columns floor at 420px so six analyses are readable rather
      than three cramped ones with the artifacts hidden
- [ ] Verified visually by a person (see below)

**Verified:** `tsc --noEmit` clean, production build clean (four routes, 131 kB first
load), every route renders, and the whole loop exercised through the proxy against a
running API — deliberate → card → resolve → per-module verdicts → history →
calibration → per-module recall. `tests/test_web_contract.py` now guards the
hand-maintained TS mirror after two new stream events drifted out of it unnoticed.

**Not verified:** how it actually looks. There is no browser automation in this
setup, so the rendering is confirmed only by types, build, and payload shape.

**Exit criterion — not yet met.** A non-technical person asks a real question and,
unprompted, correctly identifies which module they disagree with and why. That is a
test with a person in it, and it has not been run.

---

## Phase 2 — Memory and continuity ✅ *core built*

- [x] **SQLite, not Postgres** (ADR-024, superseding ADR-008's plan). One file, WAL,
      versioned migrations via `PRAGMA user_version`. Filter in SQL on denormalised
      columns; hydrate the full model from a `doc` JSON column.
- [x] FTS5 + BM25 recall with `porter` stemming, replacing hand-rolled term overlap.
      User text is never interpolated into a `MATCH` expression — every term is
      extracted and quoted, because raw text containing `AND`, `NEAR`, `*` or `-` is
      valid FTS syntax and would silently mean something else.
- [x] Deliberations, cards and per-module memories all persisted
- [x] Per-module memory extraction — six rules (`fact`, `opportunity`,
      `power_structure`, `emotional`, `workflow`, `promise`), run at resolution
- [x] Recall injected into stage 1 as attributed, arguable evidence
- [x] `app.cli migrate` imports legacy JSON history; idempotent upserts, so running
      it twice neither duplicates nor clobbers newer rows
- [x] **Projects** — decisions grouped under an ongoing situation. `POST /projects`,
      `app.cli projects --new`, `ask --project <id>`. Cards, deliberations *and*
      memories carry the project, and recall prefers same-project memories, which is
      what stops a side project bleeding into a salary conversation.
- [x] **Replay** — `POST /cards/{id}/replay`, `app.cli replay <card>`. Re-decides a
      resolved card against today's programs and grades it against the outcome that
      actually happened, reporting each module's verdict then versus now.

      This is how a module gets improved without the drift ADR-018 forbids: the
      resolved corpus becomes a test set for the council itself. The correctness
      problem is leakage and it is severe — memories extracted from the card describe
      what happened, priors computed from it encode the verdict — so both are withheld
      for the duration and the withheld count is reported (ADR-025).

**Verified.** Tests against a **real database** in a temp file — migrations,
idempotent re-open, WAL, status filtering, BM25 ranking, stemming, module scoping,
hostile FTS input, trigger-maintained deletes, timezone round-tripping, and a
two-process restart proving history survives. Plus the replay leak guard, asserted
against *both* store implementations, because `recall` is written twice — once in Python
and once in SQL — and a guarantee holding in only one of them is not a guarantee.

A flaky test here turned out to be a real bug: Windows' clock advances in ~15.6 ms steps,
so a burst of decisions shares one `created_at`, and with the tie unbroken "newest first"
returned the oldest. Fixed with `rowid DESC` / insertion-order tie-breakers and pinned by
`tests/test_store_ordering.py` across all three stores.

**Exit criterion — partially met.** Persistence, projects, per-module extraction and
replay all work. The full criterion — a follow-up two weeks later where the psychologist
recalls the emotional context while the analyst recalls the facts — needs two weeks and
real decisions.

---

## Phase 3 — Calibration (the defensible phase) ✅ *core built*

- [x] Resolution capture: `chose` as free text, `surprises` first-class
      (`POST /cards/{id}/resolve`, `app.cli resolve`)
- [x] Blind grader: verdict per module, `followed`, `falsifier_fired`,
      `chose_was_proposed` — never shown any confidence score (ADR-021)
- [x] `untested` as a first-class verdict, excluded from accuracy but counted
      against execution rate
- [x] Human override of any verdict (`PATCH /cards/{id}/verdict/{module}`)
- [x] Per-module Brier scores, hit rates, execution rates, falsifier-fire rates,
      and the same broken out per domain — computed in Python, never by a model
- [x] Each module's own `success_metrics` answered from the outcome and tallied
- [x] `Prior` generation with `evidence_count ≥ 3`, every prior citing its cards,
      injected into stage 1 as arguable memory
- [x] Prior rules: calibration gap, low execution, domain strength/weakness, a
      module failing its own declared metric, off-menu choices, unpredicted events
- [x] Display honesty: nothing shown below n=8 unless explicitly asked
- [x] Cards carry status (`open` / `due` / `resolved`) driven by `check_on`
- [x] Due-card reminders: `GET /reminders`, plus a one-line nudge the CLI prints
      after any command when a check-in has come up. No daemon — a card schedules
      its own follow-up; something just has to mention it.
- [x] Memory extraction per module — six extraction rules, run at *resolution* (not
      at deliberation time: before the outcome you only know what the user claimed,
      afterwards you know which of it mattered). `learning/extraction.py`
- [x] `recall()` is lexical overlap weighted by salience and recency, not
      salience-only and not embeddings (ADR-023). `GET /memories/{module}` exposes it
      so retrieval is inspectable rather than magic.
- [x] **Web UI for the loop** — `/history` (cards, due first, status filter),
      `/cards/[id]` (the card, the resolution form, the grader's verdicts, and a
      one-click override per module), `/calibration` (scores with the n≥8 rule and the
      withheld count stated, plus the priors each module will be told next run). A nav
      badge counts what is due, because the loop only closes if somebody comes back.

**Verified.** 21 tests covering the maths in both directions, plus an end-to-end
test that deliberates four times, resolves and grades each, and asserts a computed
prior with real counts arrives in the next run's stage-1 prompt. Live on the CLI:

```
module        domain             n    hit   conf   over   brier   exec
strategist    negotiation        5   100%    55%  -0.45   0.203   100%
```

**Exit criterion — not yet met.** It needs real resolved decisions, and there is no
shortcut: the loop is built, but ~8–10 genuinely resolved cards are required before
any number here is a measurement rather than a rounding artefact.

This is the phase nobody else can copy. The programs are an afternoon's work; the
outcome corpus is not.

---

## Phase 4 — Interface and reach ✅

- [x] **Stage re-run** — `POST /deliberations/{id}/rerun`, `app.cli rerun`. Re-runs
      one module from one named stage with new facts, carrying every earlier artifact
      untouched, then re-synthesises. This is what ADR-011 was for: because each
      stage is a separately validated artifact, "re-run the strategist's leverage
      stage knowing the investor's position" is an operation, not a rebuild. Tested
      at `deep` depth by asserting the carried artifacts are byte-identical to the
      seed and that no call was made for them.
- [x] **Refinement** — `POST /deliberations/{id}/refine`, `app.cli refine`. Answer
      the unknowns the council raised and deliberate again knowing them.
- [x] **Derive, never mutate** — both produce a new deliberation with `derived_from`
      and a `Rerun` record; the original is immutable (ADR-022).
- [x] **Interject mid-deliberation** — `POST /council/live/{run_id}/inject`. A run is
      addressable from its first event (`run_started`), so a client can answer an
      unknown the moment it sees one raised. Every batch that has not started picks
      the fact up; batches in flight are untouched, so a stage's artifact is always
      explicable by the context it was handed. Late facts are **labelled** as late
      rather than merged silently — earlier stages genuinely did not have them.
- [x] **MCP server** — `python -m app.mcp`. JSON-RPC over stdio on the standard
      library only; MCP is newline-delimited JSON-RPC 2.0 and the four methods needed
      are ~150 lines, against an SDK that would pin us to its release cycle. Six
      tools: `consult`, `list_modules`, `get_deliberation`, `record_outcome`,
      `track_record`, `pending_checkins`.

      The tools are deliberately **not** a mirror of the HTTP API. `consult` returns
      the recommendation, the disagreements, the minority opinions and the council's
      blind spot — a summary an agent can act on — and hands back a `deliberation_id`
      for the 40k-token transcript. Returning everything would blow the caller's
      context and bury the part that matters. Tested at the wire level (a missing
      `isError`, an answered notification, a schema that disagrees with its handler
      are the mistakes that actually break clients).
- [x] **Resumable deliberations** — `GET /council/resumable`,
      `POST /council/resumable/{id}/resume`, `DELETE /council/resumable/{id}`,
      `app.cli resume`. A deliberation that dies mid-flight — closed laptop, exhausted
      free-tier quota, dropped provider — is saved as a `Checkpoint` and resumed by
      handing each module back its own artifacts and restarting at the first stage it had
      not finished. **Partial** module runs survive, not just completed ones.
- [x] **A provider outage is no longer an abstention.** `ProviderError` used to be caught
      by the same handler as `ArtifactInvalid`, so a quota exhaustion produced a
      "complete" deliberation with six empty runs and wrote a Decision Card to the corpus
      — which would later be recalled as evidence and graded. The handlers are now split,
      and `ProviderUnavailable` carries the partial run out with it. This was the more
      valuable half of the feature (ADR-027).
- [x] **Voice** — `app.cli brief`. Per-module voices, but the script comes first: the
      recommendation, its falsifier, up to three dissents each spoken by the module that
      holds them, the veto, the blind spot. About ninety seconds, enforced as a test bound
      rather than hoped for. Free (`edge-tts`), and the script is still produced when no
      engine is installed (ADR-028).
- [x] **Mobile** — responsive layout plus a PWA manifest with shortcuts to the two screens
      worth opening on a phone. The phone job is resolving a due card, not deliberating;
      that needs a form that does not zoom on focus, not a native app (ADR-029).
- [x] **LangGraph — the trigger fired, and the answer was no.** ADR-007 deferred it until
      *execution had to survive the process*. That arrived, and it cost a Pydantic model,
      one SQLite table and a `resume_from` argument: because every stage is a separately
      validated artifact (ADR-011), the resume point is derivable from which artifacts
      exist, so there is no interpreter state to serialise. Adopting a graph runtime now
      would mean re-expressing six programs in someone else's control flow to gain
      persistence we already have (ADR-027).

**Exit criterion — met.** A deliberation interrupted by an exhausted free-tier quota resumes
in a *different process* and reaches a synthesis, with no module re-answering a stage it had
already completed.

Demonstrated by `scripts/phase4_exit.py`, deliberately as two separate interpreter runs
rather than as a test, because the claim is about surviving the process:

```
process 1  quota closed mid-run: ethicist: provider unavailable — HTTP 429
           crashed after 14 calls, in phase 'reason'
           5 module(s) complete, 1 partial   (ethicist: 6 of 7 artifacts banked)

process 2  a new process found checkpoint 8b16375ece47 on disk
           resumed and synthesised. 6 runs, 2 new calls
           35 banked artifact(s) from 5 module(s) carried through byte-identically
           abstentions: none
```

Two new calls, not fourteen. Artifacts are compared by hash, not by presence, so a stage
that silently re-ran would fail the check.

**Running it is what found the bug the suite could not.** `tests/test_resume.py` passed
throughout against `InMemoryStore` — which cannot test durability at all. In two processes,
`FileStore` turned out to inherit a RAM-only `save_checkpoint`, losing every checkpoint on
restart without saying so, and the shipped `.env` still selected that legacy store despite
ADR-024 making SQLite the default. Both fixed; `tests/test_checkpoint_durability.py` now
re-opens each durable store over the same directory, and fails by name if any future write
path is left inherited (ADR-027).

---

## Phase 5 — Marketplace *(authoring built)*

- [x] **Divergence harness** — `learning/divergence.py`, `GET /divergence`,
      `app.cli divergence [--live]` (ADR-026). Structural half — artifact distinctness,
      critique topology, bias-detector coverage — reads only the specs and runs in CI.
      Behavioural half runs the eight-decision battery in `learning/battery.yaml` and
      measures dissent, critique yield and stance similarity.

      Built before the marketplace on purpose: it is a quality gate for the existing six,
      not just plumbing for future modules. It reports that each of the six owns six
      unique artifact types with zero overlap — and, crucially, that the **mock council
      fails it** at 1.00 stance overlap. That failure is the evidence the instrument
      detects anything at all; without it, a passing score on the real six would mean
      nothing.
- [x] **Authoring, validation and quarantine** — `app.cli modules [--load|--activate|
      --retire|--delete]`, `GET/PUT/POST/DELETE /catalog/...` (ADR-030). A user module is
      *the same* `AgentProgram` the engine already executes, stored in SQLite (schema v4)
      rather than dropped in the package directory.

      Two properties carry the design. First, **the engine never learns that user modules
      exist**: an authored module runs through `run_program` with no new code path and no
      branch on origin anywhere — which is ADR-011 finally paying for itself. Second,
      **a broken module cannot take the server down.** Built-ins stay loud (a malformed
      built-in still refuses to boot, because that is a developer error); user content gets
      quarantined with its full error list and excluded from every preset. A draft that
      won't save is a draft nobody can fix.

      Authored modules are held to the *same* ten rules — `loader.rule_violations` is one
      rulebook with two failure modes — and `with:<module>` runs the built-in six plus one
      authored module on the same question, which is the shape the exit criterion needs.
- [x] **Declarative artifact vocabulary** — the other half of "no code". One artifact kind,
      `Table`, plus a `TableSpec` on the stage producing it: `min_rows`, `required`,
      `distinct`, `required_tags`, `ranges`, `sums_to`, and `covers` (across a stage
      boundary). Every rule was **extracted** from a shape the built-in validators already
      assert, and the proof is a test: the vocabulary restates `OptionSet`'s real invariant —
      ≥7 options, five required tags, no two labels alike — and rejects each violation the
      hand-written Python does.

      Each rule is tested in both directions, because a declarative rule that never fails is
      decoration. The loader refuses specs that *look* like guarantees but cannot fire: a
      column not in `columns`, a `covers` pointing forward, a spec on a non-`Table` stage,
      a spec with no constraint at all, and a `covers` into the same group — grouped stages
      become one call, so the covered artifact would not exist yet. That last rule caught a
      bug in the shipped example module.

      What it cannot express is named rather than hidden (ADR-030): recursive structures and
      cross-field semantics stay hand-written, so an authored module is held to a real but
      weaker standard than the six.
- [ ] Module builder *UI* — the CLI takes YAML today, which is the format the six are
      written in, so copy-and-edit already works. A form is presentation over the same model.
- [ ] Sharing, forking, versioning of modules, presets, and whole councils. Deliberately
      last: importing a stranger's module means running their prose inside a system prompt,
      which needs a review step and its own decision.
- [ ] Domain councils: hiring, medical, legal, product

**Exit criterion — not yet met.** A user-authored module must *measurably* change the
recommendation on a decision where the built-in six agreed. What exists: an authored module
runs as a seventh council member (`with:historian`, 17 calls at `quick`), produces validated
artifacts, is critiqued by the modules it names, and appears in the synthesis. What is
missing is the *measurement* — the divergence harness (ADR-026) has to be pointed at a
`with:` preset and run against a real provider, because the mock council agrees with itself
by construction (1.00 stance overlap) and therefore cannot show one module moving a verdict.
`scripts/example-module.yaml` is the module the criterion will be measured with.
