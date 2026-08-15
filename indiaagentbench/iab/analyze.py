"""Turn trajectory logs into the numbers the hypotheses stand or fall on.

The headline artefact is the **survival curve**: for each condition, the
fraction of trajectories still on the correct path at checkpoint depth k.

That formulation is deliberate. A single pass rate collapses "never found the
booking" and "did everything right then fumbled the GST" into the same zero,
and those are opposite findings. H1 says degradation *compounds with depth*, so
the evidence is not a gap in the final number -- it is the curves for C1 and C3
fanning apart as k grows. If they sit parallel, degradation is additive and H1
is false, which is worth knowing and worth publishing.

    python -m iab.analyze
    python -m iab.analyze --csv results.csv
"""
import argparse
import csv
import json
from collections import defaultdict

from .common import RUNS


def load_runs():
    rows = []
    for path in sorted(RUNS.glob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def key(r):
    return (r["model"], r["domain"], r["condition"])


def summarise(rows):
    """One row per (model, domain, condition)."""
    groups = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)

    out = []
    for (model, domain, cond), rs in sorted(groups.items()):
        n = len(rs)
        depth = [r["checkpoint_depth"] / max(r["checkpoints_total"], 1) for r in rs]
        out.append({
            "model": model, "domain": domain, "condition": cond, "n": n,
            "pass_rate": sum(r["passed"] for r in rs) / n,
            "mean_depth": sum(depth) / n,
            "mean_steps": sum(r["steps"] for r in rs) / n,
            "clarified": sum(bool(r.get("asked_clarification")) for r in rs) / n,
            "max_steps_hit": sum(r["stop_reason"] == "max_steps" for r in rs) / n,
        })
    return out


def survival(rows, max_k=6):
    """P(reached depth >= k | the task has at least k checkpoints). The H1 plot.

    The conditioning matters. Tasks carry different numbers of checkpoints, so
    an unconditional P(depth >= k) counts a 3-checkpoint task as having died at
    k=4 even when it completed perfectly -- which reads as a collapse in deep
    survival that is pure artefact. Only trajectories that *could* have reached
    depth k are in the denominator.

    Returns {group: [(k, rate, n_eligible), ...]}, carrying n so a point
    computed from two tasks is never mistaken for a solid one.
    """
    groups = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)

    curves = {}
    for g, rs in sorted(groups.items()):
        points = []
        for k in range(1, max_k + 1):
            eligible = [r for r in rs if r["checkpoints_total"] >= k]
            if not eligible:
                break
            hit = sum(1 for r in eligible if r["checkpoint_depth"] >= k)
            points.append((k, hit / len(eligible), len(eligible)))
        curves[g] = points
    return curves


def failure_modes(rows):
    """Coarse taxonomy from the verifier's own complaint text.

    Deliberately derived from the deterministic reasons rather than an LLM
    label, so the taxonomy is reproducible. H2 predicts `wrong_entity` rises
    faster than the others in the romanized conditions.
    """
    buckets = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if r["passed"]:
            continue
        g = key(r)
        for reason in r["reasons"]:
            low = reason.lower()
            if "refund recorded as" in low or "rules give" in low:
                tag = "arithmetic"
            elif "cancelled" in low and "expected" in low:
                tag = "wrong_entity"
            elif "not eligible" in low or "recorded reasons" in low:
                tag = "wrong_rule"
            elif "no refund recorded" in low or "no eligibility decision" in low \
                    or "never called" in low:
                tag = "incomplete"
            elif "expected no" in low or "who is not eligible" in low:
                tag = "overreach"
            else:
                tag = "other"
            buckets[g][tag] += 1
        if r.get("asked_clarification"):
            buckets[g]["asked_clarification"] += 1
    return buckets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="write the summary table here")
    args = ap.parse_args()

    rows = load_runs()
    if not rows:
        raise SystemExit(f"no runs found in {RUNS}")

    table = summarise(rows)
    w = max(len(t["model"]) for t in table)
    print(f"{'model':<{w}}  {'domain':<8} {'cond':<5} {'n':>3} "
          f"{'pass':>6} {'depth':>6} {'steps':>6} {'clarif':>7}")
    print("-" * (w + 47))
    for t in table:
        print(f"{t['model']:<{w}}  {t['domain']:<8} {t['condition']:<5} {t['n']:>3} "
              f"{t['pass_rate']:>6.0%} {t['mean_depth']:>6.0%} "
              f"{t['mean_steps']:>6.1f} {t['clarified']:>7.0%}")

    print("\nsurvival  P(depth >= k | task has >= k checkpoints)   [n in brackets]")
    for (model, domain, cond), curve in survival(rows).items():
        label = f"{model} / {domain} / {cond}"
        cells = " ".join(f"k{k}:{v:>4.0%}[{n}]" for k, v, n in curve)
        print(f"  {label:<40} {cells}")

    fm = failure_modes(rows)
    if fm:
        print("\nfailure modes")
        for g, tags in fm.items():
            print(f"  {' / '.join(g)}")
            for tag, count in sorted(tags.items(), key=lambda x: -x[1]):
                print(f"      {tag:<20} {count}")

    conds = {t["condition"] for t in table}
    if len(conds) < 2:
        print("\nOnly one condition present. The comparison this benchmark exists "
              "to make needs at least C1 and one non-English condition.")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(table[0]))
            wr.writeheader()
            wr.writerows(table)
        print(f"\nsummary -> {args.csv}")


if __name__ == "__main__":
    main()
