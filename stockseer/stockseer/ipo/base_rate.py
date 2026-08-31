"""The measured listing gain the alert quotes, readable without numpy.

This exists as its own module for one reason: **the alert path must import on a
bare Python.** The IPO calendar job runs on a GitHub runner with no
``pip install`` at all, because the whole scan is standard library and skipping
the install keeps it to about thirty seconds.

That guarantee was quietly broken when the message builder started quoting the
base rate. ``load_base_rate`` itself needs nothing but ``json`` and ``date``,
but it lived in ``study.py``, which imports numpy and pandas at module level to
do the actual research. Importing one function dragged the entire scientific
stack in behind it, and the daily job died with ``ModuleNotFoundError: No
module named 'numpy'`` -- after printing the IPO it had just found, so the log
looked like it was working right up to the traceback.

Keep this module free of third-party imports. If it ever needs one, the alert
path needs a ``pip install`` step, and that trade should be made deliberately
rather than discovered on a deadline morning.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "cache"
BASE_RATE_FILE = CACHE_DIR / "listing_base_rate.json"

# Fallback only, for a machine that has never run the study. Measured Aug 2026
# over 150 mainboard listings after non-equity instruments were excluded.
FALLBACK_BASE_RATE = {"median": 0.0914, "mean": 0.1435, "win_rate": 0.71,
                      "n": 150, "computed_at": "2026-08-29"}


def load_base_rate(max_age_days: int = 45) -> dict:
    """The measured listing gain, or the fallback if it was never computed.

    Staleness is reported rather than hidden: a figure from six months of
    listings ago is still usable, but the caller should be able to say so.
    """
    try:
        d = json.loads(BASE_RATE_FILE.read_text(encoding="utf-8"))
        age = (date.today() - date.fromisoformat(d["computed_at"])).days
        d["stale"] = age > max_age_days
        d["age_days"] = age
        return d
    except (OSError, ValueError, KeyError):
        return {**FALLBACK_BASE_RATE, "stale": True, "age_days": -1}


def save_base_rate(median: float, mean: float, win_rate: float, n: int) -> None:
    """Persist the mainboard listing gain so the alert can quote it.

    It used to be a literal in calendar.py, alongside a hardcoded sample size
    in the message text. Both drifted the moment the registry refreshed, and
    nothing recomputed them -- the alert was quoting +7.3% of 176 while the
    real figures had moved to +9.1% of 150.

    Takes plain numbers rather than a ``StudySummary`` so that writing the file
    does not require importing the research module either.
    """
    try:
        BASE_RATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BASE_RATE_FILE.write_text(json.dumps({
            "median": median, "mean": mean, "win_rate": win_rate, "n": n,
            "computed_at": date.today().isoformat(),
        }, indent=2), encoding="utf-8")
        log.info("base rate saved: median %.2f%% of %d", median * 100, n)
    except OSError as exc:
        log.warning("could not save base rate: %s", exc)
