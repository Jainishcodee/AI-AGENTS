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
import hashlib
import json
from pathlib import Path

from .budget import AllEndpointsDead, Rotator
from .common import DATA, RUNS, TASKS, load_json
from .envs import REGISTRY
from .policies import POLICIES
from .providers import ENDPOINTS, BadGeneration
from .verify import checkpoint_depth, verify

MAX_STEPS = 25


def bench_version(task, system):
    """Short hash of everything that determines what a score means.

    Policy text, success assertions and checkpoints all change scores without
    changing any label. Two Gemini runs here were silently produced under an
    older policy and an older rail-005 verifier, and would have sat in the same
    results table as later runs looking directly comparable. Stamping the
    version makes that visible instead of invisible.
    """
    blob = json.dumps({"policy": system,
                       "verify": task["verify"],
                       "checkpoints": task["checkpoints"]},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:10]


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
        try:
            reply = rotator.chat(system, messages, tools)
        except BadGeneration as e:
            # The model emitted something that is not a usable tool call. That
            # ends this trajectory, but it is a measurable outcome rather than a
            # run-ending error -- and one we expect more of in the non-English
            # conditions, so it has to be scored, not crashed on.
            transcript.append({"role": "error", "error": str(e)})
            stop = "bad_generation"
            break
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
        "bench_version": bench_version(task, system),
        "asked_clarification": bool(final.strip().endswith("?")),
        "survival": survival,
        "actions": env.actions,
        "transcript": transcript,
    })
    return scored


def done_keys(path):
    """(task_id, trial) pairs already on disk, for resumption."""
    if not path.exists():
        return set()
    keys = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                keys.add((r["task_id"], r.get("trial", 0)))
            except (ValueError, KeyError):
                continue
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="key in providers.ENDPOINTS, or 'mock'")
    ap.add_argument("--domain", required=True, choices=sorted(REGISTRY))
    ap.add_argument("--condition", default="C1")
    ap.add_argument("--limit", type=int, default=0, help="stop after N tasks")
    ap.add_argument("--fresh", action="store_true", help="ignore existing results")
    ap.add_argument("--trials", type=int, default=1,
                    help="repeats per task. Generation is not deterministic even "
                         "at temperature 0, so a single trial cannot tell a real "
                         "cross-condition gap from run-to-run noise.")
    args = ap.parse_args()

    tasks = load_json(TASKS / f"{args.domain}_{args.condition}.json")
    if args.limit:
        tasks = tasks[:args.limit]

    out = RUNS / f"{args.model}_{args.domain}_{args.condition}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = set() if args.fresh else done_keys(out)
    if args.fresh and out.exists():
        # Archive, never delete. Free-tier trajectories are scarce and slow to
        # earn -- a --fresh that unlinks threw away a complete 20-task baseline
        # here, and the replacement run then died one task in on daily quota.
        n = 1
        while (bak := out.with_suffix(f".jsonl.bak{n}")).exists():
            n += 1
        out.rename(bak)
        print(f"  previous results archived -> {bak.name}")

    if args.model not in ENDPOINTS:
        raise SystemExit(f"unknown model '{args.model}'. known: {sorted(ENDPOINTS)}")
    rotator = Rotator(args.model, ENDPOINTS[args.model])

    # Trial-major order: finish a full sweep of every task before starting the
    # next repeat. A run cut short by quota then yields complete trials rather
    # than every trial of the first few tasks and nothing for the rest.
    todo = [(t, i) for i in range(args.trials) for t in tasks
            if (t["task_id"], i) not in seen]
    print(f"{args.model} / {args.domain} / {args.condition}: "
          f"{len(todo)} runs to go ({len(tasks)} tasks x {args.trials} trials), "
          f"{len(seen)} already done")

    passed = 0
    done = 0
    with open(out, "a", encoding="utf-8") as f:
        for t, trial in todo:
            try:
                res = run_task(t, rotator)
            except AllEndpointsDead as e:
                print(f"\n  stopped: {e}\n  resume later -- completed work is kept.")
                break
            res["trial"] = trial
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            f.flush()
            passed += res["passed"]
            done += 1
            mark = "pass" if res["passed"] else "FAIL"
            depth = f"{res['checkpoint_depth']}/{res['checkpoints_total']}"
            tag = f" t{trial}" if args.trials > 1 else ""
            print(f"  [{mark}] {res['task_id']}{tag}  depth {depth}  steps {res['steps']}"
                  + ("" if res["passed"] else f"  <- {res['reasons'][0]}"))

    print(f"\n{passed}/{done} passed -> {out}")


if __name__ == "__main__":
    main()
