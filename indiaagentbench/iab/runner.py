"""The evaluation loop: one model, one condition, one task set.

Three properties this has to hold, all forced by the free-tier constraint:

- **Resumable.** Results append to a JSONL keyed by task_id; a restart skips
  what is already there. You will be rate-limited mid-run, repeatedly, and a
  run that cannot resume is a run that never finishes.
- **Fully logged.** Every message and every tool call is written to disk. When
  a hosted model is silently updated six months from now, the trajectories are
  the only remaining evidence of what was actually measured.
- **Survival-aware.** Checkpoint depth is recorded after *every* tool call, not
  just at the end. Final success says an agent failed; the per-step curve says
  where it fell off, and the whole compounding-degradation hypothesis lives in
  the difference between those curves across conditions.

  python -m iab.runner --model llama-70b --domain rail --condition C1
  python -m iab.runner --model mock --domain rail --condition C1 --dry-run
"""
import argparse
import json
from pathlib import Path

from .budget import AllEndpointsDead, Rotator
from .common import DATA, RUNS, TASKS, load_json
from .envs import REGISTRY
from .policies import POLICIES
from .providers import ENDPOINTS
from .verify import checkpoint_depth, verify

MAX_STEPS = 25


def run_task(task, rotator, max_steps=MAX_STEPS):
    """Drive one trajectory to completion and score it."""
    domain = task["domain"]
    env = REGISTRY[domain](load_json(DATA / f"{domain}.json"))
    system = POLICIES[domain]
    tools = env.tools()

    messages = [{"role": "user", "content": task["user_goal"]}]
    survival = []          # checkpoint depth after each tool call
    transcript = []
    stop = "completed"

    for _ in range(max_steps):
        reply = rotator.chat(system, messages, tools)
        transcript.append({"role": "assistant", **reply})

        if not reply["tool_calls"]:
            break

        messages.append({"role": "assistant", "content": reply["text"],
                         "tool_calls": reply["tool_calls"]})
        for call in reply["tool_calls"]:
            result = env.call(call["name"], call["args"])
            messages.append({"role": "tool",
                             "tool_call_id": call["id"],
                             "name": call["name"],
                             "content": json.dumps(result, ensure_ascii=False)})
            transcript.append({"role": "tool", "name": call["name"],
                               "args": call["args"], "result": result})
            survival.append(checkpoint_depth(env, task)[0])
    else:
        stop = "max_steps"

    # Ending on a question is a distinct failure mode from acting wrongly: the
    # agent had the information and declined to use it. Policy forbids it, but
    # tagging it keeps the two separable in the failure taxonomy rather than
    # both collapsing into "did not complete".
    final = next((t["text"] for t in reversed(transcript)
                  if t["role"] == "assistant" and t.get("text")), "")
    scored = verify(env, task)
    scored.update({
        "model": rotator.model_name,
        "condition": task.get("condition", "C1"),
        "domain": domain,
        "stop_reason": stop,
        "asked_clarification": bool(final.strip().endswith("?")),
        "survival": survival,
        "actions": env.actions,
        "transcript": transcript,
    })
    return scored


def done_ids(path):
    if not path.exists():
        return set()
    ids = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                ids.add(json.loads(line)["task_id"])
            except (ValueError, KeyError):
                continue
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="key in providers.ENDPOINTS, or 'mock'")
    ap.add_argument("--domain", required=True, choices=sorted(REGISTRY))
    ap.add_argument("--condition", default="C1")
    ap.add_argument("--limit", type=int, default=0, help="stop after N tasks")
    ap.add_argument("--fresh", action="store_true", help="ignore existing results")
    args = ap.parse_args()

    tasks = load_json(TASKS / f"{args.domain}_{args.condition}.json")
    if args.limit:
        tasks = tasks[:args.limit]

    out = RUNS / f"{args.model}_{args.domain}_{args.condition}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = set() if args.fresh else done_ids(out)
    if args.fresh and out.exists():
        out.unlink()

    if args.model not in ENDPOINTS:
        raise SystemExit(f"unknown model '{args.model}'. known: {sorted(ENDPOINTS)}")
    rotator = Rotator(args.model, ENDPOINTS[args.model])

    todo = [t for t in tasks if t["task_id"] not in seen]
    print(f"{args.model} / {args.domain} / {args.condition}: "
          f"{len(todo)} to run, {len(seen)} already done")

    passed = 0
    with open(out, "a", encoding="utf-8") as f:
        for t in todo:
            try:
                res = run_task(t, rotator)
            except AllEndpointsDead as e:
                print(f"\n  stopped: {e}\n  resume later -- completed work is kept.")
                break
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            f.flush()
            passed += res["passed"]
            mark = "pass" if res["passed"] else "FAIL"
            depth = f"{res['checkpoint_depth']}/{res['checkpoints_total']}"
            print(f"  [{mark}] {res['task_id']}  depth {depth}  steps {res['steps']}"
                  + ("" if res["passed"] else f"  <- {res['reasons'][0]}"))

    print(f"\n{passed}/{len(todo)} passed -> {out}")


if __name__ == "__main__":
    main()
