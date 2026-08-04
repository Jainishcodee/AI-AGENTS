"""Stage 3: reel -> structured task or fact card, via Gemini.

This is the only part of the pipeline that needs judgement, so it's the part
worth reviewing before any app work happens. Runs once, offline, on the PC --
the phone only ever reads the finished JSON.

  python distill.py --sample      # just the 20-item proof set
  python distill.py               # everything in items.json
"""
import argparse
import json
import time

import requests

from common import DATA, load_json, write_json

ENV = r"g:\AI AGENTS\Jarvis\.env"

# Free-tier daily request quotas are per-model and small (gemini-3.6-flash is
# only 20/day), so a 154-item run has to spread across models. Ordered best
# quality first; a run drops to the next only when the current one is used up
# for the day.
MODELS = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"

DOMAINS = ["fitness", "finance", "decision-making", "career", "tech", "health",
           "skincare", "style", "relationships", "mindset", "study",
           "spirituality", "food", "travel", "productivity", "other"]

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["task", "fact", "skip"]},
        # Why it was skipped decides whether transcribing the video would help.
        # This is what drives the pass-2 retry queue, so it matters more than it looks.
        "skip_reason": {"type": "string",
                        "enum": ["needs_video", "entertainment", "promotional", "empty", "n/a"]},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "domain": {"type": "string", "enum": DOMAINS},
        "tags": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "evidence": {"type": "string"},
        # task-only
        "steps": {"type": "array", "items": {"type": "string"}},
        "effort": {"type": "string", "enum": ["quick", "session", "project"]},
        "recurrence": {"type": "string", "enum": ["once", "daily", "weekly"]},
        # fact-only
        "claim": {"type": "string"},
        "why": {"type": "string"},
        "applicability": {"type": "string"},
    },
    "required": ["kind", "skip_reason", "title", "summary", "domain", "tags",
                 "confidence", "evidence"],
}

SYSTEM = """You turn a saved Instagram reel into ONE structured card for a personal productivity app.

You get the caption, hashtags, creator, and (sometimes) an automatic speech transcript.
The transcript is machine-generated and may be rough, especially for Hindi/Gujarati/Hinglish.
Read through the roughness, but never invent content that isn't there.

Choose exactly one kind:

- "task"  - the reel tells the user to DO something concrete (a workout, a habit,
            a recipe, a tool to try, a skill to practise, a place to visit).
            title: imperative, specific, second person implied. "Do 3x12 incline push-ups", not "Push-up video".
            steps: the concrete actions, in order. Empty if the reel gives none.
            effort: quick = under 15 minutes. session = 1-3 hours. project = spans days or weeks.
            recurrence: once, daily, or weekly.

- "fact"  - the reel states knowledge, a rule, a principle, a piece of news.
            claim: the single rule or fact, stated in one sentence, standalone.
            why: the reasoning or mechanism behind it, if given.
            applicability: the concrete situation where this is worth recalling.
            Always fill applicability with a real situation. Never write "None".

- "skip"  - pure entertainment, a meme, a song, an ad, or too little content to
            be either. Do NOT force a card out of nothing. Skipping is correct
            and expected for a good share of reels.

skip_reason is required, and for kind "task" or "fact" it must be "n/a".
When you skip, it decides whether we bother transcribing the video later, so be precise:
- "needs_video"   - the caption is a HOOK or TEASER for real content that is spoken
                    or shown in the video, and you'd likely produce a good card if you
                    could hear it. Titles like "5 rules for X", "here's the secret to Y",
                    "watch till the end", or a listicle whose items aren't actually written
                    out. A long caption can still be a pure hook -- judge substance, not length.
- "entertainment" - a meme, song edit, film clip, or anecdote. No card exists even with audio.
- "promotional"   - an ad, product push, or podcast teaser selling something.
- "empty"         - genuinely nothing there at all.

Rules:
- evidence: quote the exact phrase from the caption or transcript that justifies the card.
  If nothing justifies it, use kind "skip".
- confidence: "high" only when the source clearly states it. "low" when you are
  reading between the lines or the transcript is garbled.
- summary: 1-3 plain sentences a person can act on without opening the reel.
- tags: 3-6 lowercase keywords for search. Include the specific nouns, not just the domain.
- Write in English even when the source is Hindi/Gujarati.
"""


def api_key():
    for line in open(ENV, encoding="utf-8"):
        if line.startswith("GEMINI_API_KEY"):
            return line.split("=", 1)[1].strip()
    raise SystemExit("GEMINI_API_KEY not found in Jarvis/.env")


def build_prompt(item):
    tx = item.get("transcript", "").strip()
    parts = [
        f"Creator: @{item['owner_user']} ({item['owner_name']})",
        f"Collection it was saved into: {item['collection']}",
        f"Caption: {item['caption'] or '(empty)'}",
        f"Hashtags: {' '.join('#' + h for h in item['hashtags']) or '(none)'}",
    ]
    if item["kind_hint"] != "auto":
        parts.append(f"The user files this collection under: {item['kind_hint']}s "
                     f"(a hint, not a rule -- override it if the content clearly disagrees).")
    parts.append(f"Speech transcript: {tx if tx else '(none available)'}")
    return "\n".join(parts)


class Budget:
    """Tracks which models still have quota left today."""

    def __init__(self, models):
        self.models = list(models)
        self.i = 0

    @property
    def model(self):
        return self.models[self.i] if self.i < len(self.models) else None

    def exhausted(self):
        """Current model is out of daily quota -- move to the next one."""
        dead = self.model
        self.i += 1
        if self.model:
            print(f"    ! {dead} daily quota used up -> switching to {self.model}")
        else:
            print(f"    ! {dead} daily quota used up -- no models left")
        return self.model


def call(key, prompt, budget, retries=3):
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
        },
    }
    last = "no model available"
    while budget.model:
        delay = 5
        for _ in range(retries):
            try:
                r = requests.post(ENDPOINT.format(budget.model),
                                  headers={"x-goog-api-key": key},
                                  json=body, timeout=120)
                if r.status_code == 429:
                    msg = r.text
                    if "PerDay" in msg:      # daily cap, waiting won't help
                        last = f"{budget.model} daily quota exhausted"
                        break
                    last = "429 per-minute rate limit"
                    time.sleep(delay)        # per-minute cap, backing off does help
                    delay *= 2
                    continue
                r.raise_for_status()
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(txt)
            except Exception as e:
                last = str(e)
                time.sleep(delay)
                delay *= 2
        if "daily quota exhausted" not in last:
            break                            # a real failure, not a quota one
        budget.exhausted()
    # Flagged with an error key so a later run retries it instead of trusting it.
    return {"kind": "skip", "skip_reason": "empty", "title": "", "error": last,
            "summary": f"ERROR: {last}", "domain": "other", "tags": [],
            "confidence": "low", "evidence": ""}


# effort -> which bucket it lands in. Deterministic, not the model's call.
HORIZON = {"quick": "today", "session": "short_term", "project": "long_term"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--sleep", type=float, default=3.0, help="pacing between calls")
    args = ap.parse_args()

    items = load_json(DATA / "items.json")
    if args.sample:
        ids = set(load_json(DATA / "sample.json"))
        items = [i for i in items if i["id"] in ids]

    key = api_key()
    out_path = DATA / ("distilled_sample.json" if args.sample else "distilled.json")
    done = {}
    if out_path.exists():
        have_tx = {i["id"] for i in items if len(i.get("transcript", "").strip()) > 30}
        for d in load_json(out_path):
            if d.get("error"):
                continue  # a failure, not a verdict -- retry it
            if d.get("skip_reason") == "needs_video" and d["id"] in have_tx:
                continue  # pass 1 gave up for want of audio; we have it now, so ask again
            done[d["id"]] = d

    budget = Budget(MODELS)
    results, t0 = [], time.time()
    for n, it in enumerate(items, 1):
        if it["id"] in done:
            results.append(done[it["id"]])
            continue
        card = call(key, build_prompt(it), budget)
        card["model"] = budget.model or ""
        card["id"] = it["id"]
        card["url"] = it["url"]
        card["collection"] = it["collection"]
        card["owner_user"] = it["owner_user"]
        card["used_transcript"] = bool(it.get("transcript", "").strip())
        if card["kind"] == "task":
            card["horizon"] = HORIZON.get(card.get("effort", "session"), "short_term")
        results.append(card)
        print(f"[{n}/{len(items)}] {it['id']:<14} {card['kind']:<5} "
              f"{card.get('confidence',''):<6} {card.get('title','')[:60]}")
        write_json(out_path, results)  # checkpoint every item; free tier is flaky
        time.sleep(args.sleep)

    write_json(out_path, results)
    kinds = {}
    for r in results:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"\n{len(results)} cards in {time.time() - t0:.0f}s  {kinds}")
    print(f"-> {out_path}")


if __name__ == "__main__":
    main()
