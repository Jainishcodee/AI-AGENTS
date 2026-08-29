"""Backfill historical subscription data and test what it predicts.

The listing-gain study answers "what did allotment pay?" but not the question
that decides where to apply: **does heavy subscription buy you a bigger pop?**

If it does, the terrible odds on a hyped issue are at least partly compensated
and the raw expected-value ranking is too harsh. If it does not, hype is pure
cost -- you pay in probability and receive nothing back -- and the arithmetic
in `apply.py` stands unqualified.

Nothing in StockSeer could answer this before, because `past_issues()` returns
eleven fields and none of them is subscription. The unlock is that NSE's
`ipo-active-category` endpoint keeps answering for issues that closed and
listed long ago: probes returned real figures for every year tested back to
2003. So the independent variable was retrievable all along, one symbol at a
time.

Fetching is deliberately slow and resumable. This walks a few hundred symbols
against an exchange that rate-limits and geo-blocks, so it caches every result
and can be re-run to fill gaps rather than starting over.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "cache"
HISTORY_FILE = CACHE_DIR / "nse_subscription_history.json"


def load_history() -> dict[str, dict]:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_history(hist: dict[str, dict]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(hist, indent=1), encoding="utf-8")


def backfill(limit: int | None = None, pause: float = 1.2,
             refresh: bool = False) -> dict[str, dict]:
    """Fetch final subscription for past mainboard issues, resumably.

    Symbols already present are skipped unless `refresh`, so an interrupted run
    costs nothing to resume. Misses are recorded too -- a symbol NSE will never
    answer for should not be retried on every future run.
    """
    from .registry import NseUnavailable, past_issues, subscription

    hist = load_history()
    todo = [i for i in past_issues(mainboard_only=True) if i.listed]
    if not refresh:
        todo = [i for i in todo if i.symbol not in hist]
    if limit:
        todo = todo[:limit]

    print(f" {len(hist)} already cached, fetching {len(todo)} more")
    got = 0
    for n, ipo in enumerate(todo, 1):
        try:
            s = subscription(ipo.symbol)
        except NseUnavailable:
            print(f"   NSE stopped answering after {n - 1}; saving and stopping")
            break
        except Exception as exc:                       # one bad symbol, not a run
            log.debug("%s: %s", ipo.symbol, exc)
            s = None

        hist[ipo.symbol] = {
            "retail_x": s.retail_x if s else None,
            "qib_x": s.qib_x if s else None,
            "nii_x": s.nii_x if s else None,
            "listing_date": ipo.listing_date,
            "issue_price": ipo.issue_price,
        }
        if s and s.retail_x is not None:
            got += 1
        if n % 20 == 0:
            save_history(hist)
            print(f"   {n}/{len(todo)} fetched, {got} with retail figures")
        time.sleep(pause)

    save_history(hist)
    print(f" saved {len(hist)} records to {HISTORY_FILE.name}")
    return hist


# --------------------------------------------------------------------------- #
# The question this data exists to answer
# --------------------------------------------------------------------------- #
def study_subscription(refresh: bool = False, buckets: int = 5) -> None:
    """Does subscription level predict the listing gain, and the EV after odds?

    Two columns matter and they point in opposite directions. `gain` is what
    allotment paid; if it rises with subscription, hype is at least partly
    compensated. `EV/lakh` is that gain multiplied by the probability of
    getting any, which is what a rupee of your capital actually expects.
    """
    import numpy as np
    from scipy import stats

    from .registry import past_issues
    from .study import measure

    hist = load_history()
    if not hist:
        print(" no subscription history -- run the backfill first.")
        return

    by_symbol = {i.symbol: i for i in past_issues(mainboard_only=True)}
    rows = []
    for sym, rec in hist.items():
        r = rec.get("retail_x")
        ipo = by_symbol.get(sym)
        if r is None or r <= 0 or ipo is None:
            continue
        out = measure(ipo)
        if out is None:
            continue
        rows.append((r, out.allotment_gain))

    if len(rows) < 30:
        print(f" only {len(rows)} usable pairs -- too few to say anything.")
        return

    sub = np.array([r for r, _ in rows])
    gain = np.array([g for _, g in rows])
    n = len(rows)

    print(f"\n{'=' * 72}")
    print(f" DOES SUBSCRIPTION PREDICT THE LISTING GAIN?   n = {n} mainboard IPOs")
    print("=" * 72)

    # Rank correlation, because subscription spans 0.2x to 400x and a couple of
    # extreme issues would otherwise decide a Pearson coefficient by themselves.
    rho, p = stats.spearmanr(sub, gain)
    print(f"\n  Spearman rank correlation: rho = {rho:+.3f}   p = {p:.4f}")
    print("  " + ("subscription carries real information about the gain"
                  if p < 0.05 else
                  "no reliable relationship -- hype does not buy a bigger pop"))

    edges = np.quantile(sub, np.linspace(0, 1, buckets + 1))
    print(f"\n  {'subscription':<18}{'n':>5}{'median gain':>13}{'mean':>9}"
          f"{'win':>7}{'odds':>8}{'EV/lakh':>10}")
    print("  " + "-" * 68)
    for k in range(buckets):
        lo, hi = edges[k], edges[k + 1]
        m = (sub >= lo) & (sub <= hi) if k == buckets - 1 else (sub >= lo) & (sub < hi)
        if m.sum() < 3:
            continue
        g, s = gain[m], sub[m]
        odds = np.minimum(1.0, 1.0 / s)
        # Rupees expected per lakh blocked: the payoff after the lottery.
        ev = float(np.median(odds * np.median(g) * 100_000))
        print(f"  {f'{lo:.1f}x - {hi:.1f}x':<18}{int(m.sum()):>5}"
              f"{np.median(g) * 100:>12.2f}%{g.mean() * 100:>8.2f}%"
              f"{(g > 0).mean() * 100:>6.0f}%{np.median(odds) * 100:>7.1f}%"
              f"{ev:>10,.0f}")

    print("\n  EV/lakh is what a lakh of blocked capital expects per application,")
    print("  before the ~5 days it stays blocked. Compare it against a deposit.")
    print("=" * 72 + "\n")

    save_gain_curve(sub, gain)


# --------------------------------------------------------------------------- #
# Expected gain as a function of subscription
# --------------------------------------------------------------------------- #
GAIN_CURVE_FILE = CACHE_DIR / "listing_gain_curve.json"

# Fallback measured Aug 2026 over 382 mainboard listings. Each entry is
# (minimum retail subscription, median gain, win rate, n).
FALLBACK_CURVE = [
    [0.0, 0.0000, 0.43, 77],
    [1.3, -0.0082, 0.43, 76],
    [3.5, 0.0611, 0.67, 76],
    [9.3, 0.1238, 0.72, 76],
    [22.9, 0.3824, 0.87, 77],
]


def save_gain_curve(sub, gain, buckets: int = 5) -> None:
    """Persist expected gain as a function of subscription.

    The alert used to apply one global median to every issue, which is wrong in
    both directions: it overstates a barely-subscribed issue, whose median gain
    is actually negative, and understates a heavily-subscribed one by roughly
    fourfold. Subscription and gain correlate at rho = +0.49 over 382 listings,
    so conditioning on it is not a refinement -- it changes the sign of the
    advice at the bottom of the range.
    """
    import numpy as np

    edges = np.quantile(sub, np.linspace(0, 1, buckets + 1))
    curve = []
    for k in range(buckets):
        lo, hi = edges[k], edges[k + 1]
        m = (sub >= lo) & (sub <= hi) if k == buckets - 1 else (sub >= lo) & (sub < hi)
        if m.sum() < 3:
            continue
        g = gain[m]
        curve.append([float(lo), float(np.median(g)),
                      float((g > 0).mean()), int(m.sum())])
    try:
        GAIN_CURVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        GAIN_CURVE_FILE.write_text(json.dumps(curve, indent=1), encoding="utf-8")
        log.info("gain curve saved: %d buckets", len(curve))
    except OSError as exc:
        log.warning("could not save gain curve: %s", exc)


def load_gain_curve() -> list[list[float]]:
    try:
        c = json.loads(GAIN_CURVE_FILE.read_text(encoding="utf-8"))
        return c if c else FALLBACK_CURVE
    except (OSError, ValueError):
        return FALLBACK_CURVE
