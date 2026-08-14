"""Shared paths, env loading and JSON helpers for IndiaAgentBench."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"          # seeded databases, one JSON per domain
TASKS = ROOT / "tasks"        # task sets, one JSON per domain+condition
RUNS = ROOT / "runs"          # trajectory logs, one JSONL per (model, condition)


def load_env(path=None):
    """Load KEY=value lines from .env into os.environ, without overriding.

    Called once when providers is imported, so `python -m iab.runner ...` just
    works after dropping keys in a file. Real environment variables always win,
    which keeps CI and one-off overrides predictable.
    """
    p = Path(path) if path else ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


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
