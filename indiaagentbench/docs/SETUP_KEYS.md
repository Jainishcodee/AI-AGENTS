# Getting the API keys

All free, no card required. Put them in `indiaagentbench/.env` and every command
picks them up automatically — `.env` is gitignored, so keys never reach the repo.

```
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=...
HF_TOKEN=hf_...
```

Verify at any time with:

```bash
python -m iab.check_endpoints
```

One trivial tool-calling request per endpoint. It reports whether the model
exists, whether the key works, and — the part that decides inclusion — whether
the model actually emits a **native tool call** rather than prose.

---

## Groq (priority — this is the workhorse)

Free tier with genuinely usable limits, 11 open-weight models, function calling
on all of them at 131k context. This carries the Llama/Qwen baselines.

1. Go to **<https://console.groq.com>**
2. Sign in with Google, GitHub, or email. No credit card, no billing setup.
3. Left sidebar → **API Keys**
4. **Create API Key**, give it a name (e.g. `indiaagentbench`)
5. **Copy it immediately** — Groq shows the key exactly once. If you lose it,
   delete the key and make a new one.
6. Paste into `indiaagentbench/.env` as `GROQ_API_KEY=gsk_...`

Then:

```bash
python -m iab.check_endpoints --model llama-70b
```

You want `[      ok] llama-3.3-70b-versatile @ api.groq.com`.

**Watch the rate limits.** Groq's free tier caps requests *and* tokens per
minute and per day; the exact numbers are on the Limits page in the console and
they change. The harness handles this — it backs off on a 429, fails over to the
next host, and stops cleanly when a daily cap is gone, resuming later against
the same cache. You don't need to babysit a run.

## Gemini (already working)

Currently read from `Jarvis/.env`. Used for **translation drafts only**, never
for evaluation. Free-tier daily caps are per-model and small, which is why the
translator rotates across `gemini-2.5-flash` → `3.5-flash` → `3.1-flash-lite`;
it already burned through the first model generating the Hindi conditions.

To decouple it from Jarvis, copy the value into `indiaagentbench/.env`.

## HuggingFace (for the Indian model)

Needed for **BharatGen Param2-17B**, the one confirmed Indian model with tool
calling — important for the paper's framing, since a benchmark for Indian
languages that evaluates no Indian model is a weak story.

1. <https://huggingface.co/settings/tokens>
2. **Create new token** → type **Read**
3. Copy into `.env` as `HF_TOKEN=hf_...`

The routing in `ENDPOINTS` for this one is still marked UNCONFIRMED —
`check_endpoints` will tell us whether Param2 is served through Inference
Providers or needs a different path.

## Sarvam (optional)

`sarvam-105b` on `https://api.sarvam.ai/v1`. Sign up at
<https://dashboard.sarvam.ai>. Their docs do **not** confirm tool-calling support
for the 105B chat models, so this may come back `no-tools` — which is a result
worth reporting rather than a problem, since it would mean India's flagship
model needs a ReAct text adapter to be evaluated agentically at all.

## Cerebras (optional)

<https://cloud.cerebras.ai> → API Keys. Only useful as a second host for the
Llama baseline so Groq quota exhaustion doesn't stall a run mid-way.
