"""One-call live verification of every endpoint before a real run.

Model catalogues move fast and quietly -- sarvam-30b and sarvam-m were both
deprecated between this benchmark being designed and being built. Burning a
day's free-tier allowance to discover a 404 on task 3 is avoidable, so this
sends exactly one trivial tool-calling request per endpoint and reports what
came back.

It checks the thing that actually gates inclusion: **does the model emit a
native tool call?** A model that answers in prose cannot be evaluated on an
agentic benchmark without a ReAct-style text adapter, and knowing which models
need one is itself a finding worth reporting.

    python -m iab.check_endpoints
    python -m iab.check_endpoints --model sarvam-105b
"""
import argparse
import os

from .providers import ENDPOINTS, ProviderError, build

PROBE_TOOL = [{
    "name": "get_time",
    "description": "Get the current time in a city.",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}]

PROBE = [{"role": "user", "content": "What time is it in Mumbai? Use the tool."}]
SYSTEM = "You are a helpful assistant. Use the provided tools when they apply."


def check(kind, base_url, key_env, model_id):
    if not os.environ.get(key_env):
        return "skip", f"{key_env} not set"
    try:
        p = build(kind, base_url, key_env, model_id)
        reply = p.chat(SYSTEM, PROBE, PROBE_TOOL)
    except ProviderError as e:
        return "fail", str(e)[:160]
    except Exception as e:                                    # noqa: BLE001
        return "fail", f"{type(e).__name__}: {str(e)[:140]}"

    if reply["tool_calls"]:
        c = reply["tool_calls"][0]
        return "ok", f"tool_call {c['name']}({c['args']})"
    return "no-tools", f"prose only: {reply['text'][:90]!r}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="check only this model")
    args = ap.parse_args()

    names = [args.model] if args.model else sorted(ENDPOINTS)
    unknown = [n for n in names if n not in ENDPOINTS]
    if unknown:
        raise SystemExit(f"unknown model(s) {unknown}. known: {sorted(ENDPOINTS)}")

    usable = []
    for name in names:
        print(f"\n{name}")
        for spec in ENDPOINTS[name]:
            kind, base_url, key_env, model_id = spec
            status, detail = check(*spec)
            host = (base_url or "gemini").replace("https://", "").split("/")[0]
            print(f"  [{status:>8}] {model_id:<42} @ {host}")
            print(f"             {detail}")
            if status == "ok":
                usable.append((name, model_id))
                break

    print(f"\n{len(usable)}/{len(names)} models usable for the run")
    for name, model_id in usable:
        print(f"  {name:<14} -> {model_id}")
    missing = sorted(set(names) - {n for n, _ in usable})
    if missing:
        print(f"\nnot usable: {missing}")
        print("A model that returns 'no-tools' needs a ReAct text adapter before it "
              "can be evaluated -- which models those are is itself a result.")


if __name__ == "__main__":
    main()
