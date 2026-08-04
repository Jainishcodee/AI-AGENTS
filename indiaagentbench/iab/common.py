"""Shared paths and JSON helpers for IndiaAgentBench."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"          # seeded databases, one JSON per domain
TASKS = ROOT / "tasks"        # task sets, one JSON per domain+condition
RUNS = ROOT / "runs"          # trajectory logs, one JSONL per (model, condition)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def money(x):
    """Rupees, rounded to whole paise-free integers.

    Refund rules are stated in whole rupees, so carrying floats through the
    slab arithmetic would make verifiers fail on 1949.9999999 vs 1950.
    """
    return int(round(float(x)))
