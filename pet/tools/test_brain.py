"""Can the local model actually do the pet's job? Nothing else installed needed.

    python tools/test_brain.py

The pet only needs one thing from an LLM: turn a loose spoken sentence into a
strict instruction. That's a much smaller ask than "be a good chatbot", which
is why a 3.8B model on a 4GB card is a reasonable bet. This checks whether that
bet holds before any code is written against it.
"""
import json
import sys
import time
import urllib.error
import urllib.request

HOST = "http://127.0.0.1:11434"
MODEL = "phi4-mini"

SYSTEM = """You convert a user's request into JSON for a desktop assistant.
Reply with ONLY a JSON object, no prose, no markdown fence.

Schema: {"action": "<open_app|reminder|question|unknown>", "target": "<string>"}

- open_app  : they want a program launched. target = the program name only.
- reminder  : they want to be reminded of something. target = what to remind.
- question  : they asked something factual. target = the question.
- unknown   : anything else. target = "".
Never invent a program name that was not mentioned."""

CASES = [
    ("open brave for me",                    "open_app", "brave"),
    ("can you fire up spotify",              "open_app", "spotify"),
    ("launch vs code please",                "open_app", None),
    ("remind me to call mom in an hour",     "reminder", None),
    ("what's the capital of Japan",          "question", None),
    ("i'm so tired today",                   "unknown",  None),
]


def chat(system: str, user: str, timeout: int = 120) -> tuple[str, float]:
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "stream": False,
        "format": "json",              # Ollama constrains output to valid JSON
        "options": {"temperature": 0, "num_ctx": 2048},
    }).encode()
    req = urllib.request.Request(f"{HOST}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read())
    return payload["message"]["content"], time.monotonic() - t0


def main() -> int:
    try:
        urllib.request.urlopen(f"{HOST}/api/tags", timeout=5)
    except (urllib.error.URLError, OSError) as e:
        print(f"Ollama isn't reachable at {HOST} — {e}")
        return 1

    print(f"model: {MODEL}\n")
    passed, times = 0, []

    for text, want_action, want_target in CASES:
        try:
            raw, secs = chat(SYSTEM, text)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR  {text!r}: {e}")
            continue
        times.append(secs)

        try:
            got = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  FAIL   {text!r} -> not JSON: {raw[:70]!r}")
            continue

        action = str(got.get("action", "")).strip()
        target = str(got.get("target", "")).strip().lower()

        ok = action == want_action
        if ok and want_target is not None:
            ok = want_target in target

        print(f"  {'PASS' if ok else 'FAIL'}   {text!r}")
        print(f"         -> action={action!r} target={target!r}  ({secs:.1f}s)")
        passed += ok

    if times:
        print(f"\n{passed}/{len(CASES)} correct · "
              f"median {sorted(times)[len(times) // 2]:.1f}s per request")

    # The bar is intent routing, not brilliance. Below this it isn't usable.
    if passed < len(CASES) - 1:
        print("\nNot good enough for intent parsing — try qwen3:4b instead.")
        return 1
    print("\nOK — good enough to route intents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
