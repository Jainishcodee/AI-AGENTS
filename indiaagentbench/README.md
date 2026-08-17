# IndiaAgentBench

An agentic benchmark for Indian languages: can an LLM agent complete a real,
multi-step, consequential task for a user who is not writing in English?

Every Indic benchmark to date measures **understanding** — MILU, IndicParam,
ParamBench, IndicGenBench are all single-turn, mostly multiple-choice. Every
agentic benchmark measures **doing** — but in English, in Western task
environments. Nothing measures both at once for India.

## The hypothesis

Two 2026 results established that romanized input degrades Indic model
performance badly: [Script Gap](https://arxiv.org/abs/2512.10780) measured up to
**24 points** of degradation on romanized vs. native script, and
[Indi-RomCoM](https://arxiv.org/html/2606.30790) found sharp execution drops
under romanized Hinglish instructions. Both are **single-turn**. Separately, the
long-horizon agent literature shows early planning deviations propagate through
later steps.

Nobody has connected them.

> **H1 — Compounding Script Gap.** Language-form degradation compounds
> multiplicatively across agent trajectories. A 24-point single-turn gap becomes
> catastrophic over a 10-step task, meaning single-turn Indic benchmarks
> systematically *understate* how broken deployed Indic agents are.
>
> **H2 — Mechanism.** The compounding is not diffuse. Romanized input primarily
> corrupts entity/slot extraction — names, place names, scheme names, amounts —
> which poisons tool arguments, which silently derails everything downstream.

Both are falsifiable. A negative result is still a result worth publishing,
against an effect the field currently assumes without measuring.

## Design

### Conditions

The same task, the same answer key; only the user's input form changes. That is
the entire experiment.

| | Condition |
|---|---|
| C1 | English (baseline) |
| C2 | Hindi, Devanagari |
| C3 | Hindi, romanized code-mixed (~50% switching) |
| C4 | Tamil, native script |
| C5 | Tamil, romanized code-mixed |
| C6 | *stretch:* voice — TTS → ASR round trip over C3 |

**Domain policies stay in English across every condition.** Only user turns
change language. This isolates user-input language as the single independent
variable instead of confounding it with policy language, and it mirrors real
Indian deployments: business logic authored in English, users speaking Hindi or
Tamil.

### Domains

**`rail`** — booking, cancellation and refund under the real IRCTC slabs. This
is the **control**: it parallels the airline domain in τ²-bench, so C1 numbers
can be sanity-checked against published English agent results. If C1 lands
nowhere near that band, the harness is broken and no cross-language claim from
it is trustworthy.

**`schemes`** — eligibility determination and application for PM-KISAN, PM-JAY
and the National Post-Matric Scholarship. This is the domain with **no Western
analog**, and it is what makes this India's benchmark rather than a translated
one. Its task shape is genuinely different: the agent must *refuse* as often as
it acts, because submitting an application for an ineligible citizen is a real
harm — it is recorded against them and can trigger recovery proceedings.

### Scoring

Success is a **programmatic assertion on final environment state**. No LLM
judge. This is free to run, but the real reason is validity: judge calibration
drift is a live threat to agent benchmarks, since a hosted judge silently
updating between runs makes historical scores incomparable. A state assertion in
2026 means the same thing in 2028.

Beyond binary success, **checkpoint depth is recorded after every tool call**.
Final success tells you *that* an agent failed; the per-step survival curve tells
you *where* it fell off — and H1 lives entirely in how those curves differ across
conditions.

### Two design decisions worth knowing about

**Ground truth is derived, never stored.** Expected refunds are recomputed from
live environment state rather than written into task files, so a seed edit can
never silently desynchronise the answer key. This bit us once already: refund
rules originally branched on the live berth status, so cancelling a waitlisted
berth flipped it to `CANCELLED`, the clerkage rule stopped applying, and the
expected refund changed *mid-trajectory* from ₹1260 to ₹1200 — making the correct
answer fail and the wrong one pass. Berth status is now frozen at booking time.
See `test_ground_truth_survives_mutation`.

**The null baseline must score zero.** Nine of the twenty tasks are refusal
tasks, and in the first draft an agent that did literally nothing passed all
nine — a 45% floor. That would have been fatal: abstention does not degrade when
input language changes, so a large block of trivially-passed tasks would have
flattened exactly the gap the benchmark exists to measure. Refusal now requires
calling `record_decision` with the specific exclusion codes that apply, so
refusing correctly is distinguishable from refusing blindly. See
`test_null_agent_scores_zero_on_every_task`.

**Scores are stochastic — always run multiple trials.** Two identical C1 runs of
`gpt-oss-120b` disagreed on rail-004 and sch-009. Generation is not deterministic
at temperature 0: MoE routing and server-side batching both introduce variance.
So a single-trial C1-vs-C3 gap cannot be distinguished from run-to-run noise, and
the whole result rests on that comparison. `--trials 3` is the minimum; the
summary reports `flaky` (tasks the model both passes and fails on identical
input), which is the honest noise floor. **Any cross-condition gap smaller than
`flaky` is not evidence of anything.**

**Results are version-stamped.** Policy text, success assertions and checkpoints
all change what a score means without changing any label. Every result carries a
`bench_version` hash of those three, and the analyzer refuses to let mixed
versions sit in one table unremarked — two early Gemini runs were made under an
older policy and would otherwise have looked directly comparable.

### Environments are simulated, always

Nothing here touches real IRCTC, UPI, DigiLocker or any government endpoint.
That is deliberate and non-negotiable: live calls would make the benchmark
unreproducible, unrunnable by other researchers, and legally radioactive. Mock
services with honest state machines are what this kind of evaluation requires.

## Layout

```
iab/
  envs/base.py     tool-callable state machine, action logging
  envs/rail.py     IRCTC refund rules + tools
  envs/schemes.py  welfare eligibility rules + tools
  policies.py      per-domain agent rulebooks (English in all conditions)
  seed.py          hand-designed deterministic databases
  tasks_c1.py      the English task set, source for all translations
  verify.py        deterministic assertion ops + checkpoint depth
  providers.py     Gemini / OpenAI-compatible / Mock, one normalised interface
  budget.py        endpoint rotation across hosts of the *same* model
  runner.py        resumable evaluation loop
  translate.py     C2-C5 generation, with a human-override layer
  validate_conditions.py  quality gates + editable review sheet
  script_utils.py  script purity and code-mix density
  check_endpoints.py      one-call liveness probe per model
tests/             85 tests, no network, no API key
```

## Running it

```bash
python -m iab.seed                  # regenerate the seeded databases
python -m iab.tasks_c1              # regenerate the C1 task files
python -m unittest discover -s tests -v

python -m iab.check_endpoints                      # which models are actually usable
python -m iab.runner --model gpt-oss-120b --domain rail --condition C1 --trials 3
python -m iab.analyze
```

Model catalogues churn fast and silently -- `llama-3.3-70b-versatile` 404s on Groq
now, and both `sarvam-30b` and `sarvam-m` were deprecated between this benchmark
being designed and being built. Always run `check_endpoints` first: it probes for
*native tool calling*, which is what actually gates a model's inclusion.

Nothing but `requests` is needed to run the tests — they use the scripted `Mock`
provider, so the entire harness is exercised without spending a token.

### Free-tier operation

Rotation moves between **hosts serving the same weights**, never between
different models — the model is the independent variable, so substituting one
for another would quietly corrupt the comparison. (This is the key difference
from the reelflow quota rotator this grew out of, where any model that answered
was acceptable.) When every host for a model is exhausted, the run *stops*
rather than degrading; results append to JSONL keyed by task_id, so resuming
tomorrow picks up exactly where it left off.

Set whichever of these you have: `GROQ_API_KEY`, `CEREBRAS_API_KEY`,
`OPENROUTER_API_KEY`, `GEMINI_API_KEY`.

## Status

- [x] Environments, rules, seeds, verifiers, harness, **102 tests**
- [x] C1 (English): 20 tasks — 8 rail, 12 schemes
- [x] Condition pipeline: generation, quality gates, human-override layer
- [x] C2/C3 (Hindi + Hinglish): 40 tasks drafted, 0 hard failures
- [x] First live baseline: `gpt-oss-120b` on Groq, both domains
- [ ] Task set under-discriminates at the top (C1 ~88%). Needs deeper tasks —
      more checkpoints per task is also what gives the survival curve the
      resolution H1 needs
- [ ] **Native-speaker sign-off on C2/C3** — 40 drafts outstanding. Open
      `review_hindi.html`, edit in place, download the override files. This is
      the credibility blocker: unvalidated MT sinks the result regardless of how
      sound the rest is.
- [ ] C4/C5 (Tamil) — needs a Tamil validator lined up first
- [ ] Expand C1 to ~80 tasks
- [ ] Full run, survival curves, H1/H2 analysis
- [ ] Preprint, HuggingFace dataset, leaderboard

See [docs/SETUP_KEYS.md](docs/SETUP_KEYS.md) for API keys, and run
`python -m iab.check_endpoints` to see which models are actually usable.

## Prior work this builds on

- [SEATauBench](https://arxiv.org/pdf/2606.28715) — the same move for Southeast
  Asian languages (June 2026). Proof the contribution is real; proof India is
  still uncovered.
- [Script Gap](https://arxiv.org/abs/2512.10780), [Indi-RomCoM](https://arxiv.org/html/2606.30790) — the single-turn romanization gap this extends to trajectories.
- [MILU](https://arxiv.org/html/2411.02538) — the Indic understanding benchmark this complements rather than replaces.
- [MAPS](https://aclanthology.org/2026.findings-eacl.42.pdf) — multilingual agent performance and security, EACL 2026.
