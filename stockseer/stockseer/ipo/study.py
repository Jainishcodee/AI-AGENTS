"""Does the listing-day pattern actually exist?

Two strategies get conflated constantly, and they are not the same bet:

**A -- Allotment.** Apply, get shares at the issue price, sell at listing.
Your entry is the issue price, so the whole listing premium is yours.

**B -- Buy at the listing open.** No allotment, so you buy on the open market at
10:00 and sell later the same morning. Your entry is the *already-popped* price.
The premium everyone talks about is gone before you click buy; what remains is a
pure intraday momentum bet on the most volatile instrument on the exchange.

This module measures both separately. If B works, the listing open must be
systematically below the late-morning price -- that is a testable claim, not a
matter of opinion, and it is what ``run_study`` tests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data import load_prices
from .registry import IPO, past_issues

log = logging.getLogger(__name__)


@dataclass
class ListingOutcome:
    symbol: str
    company: str
    listing_date: str
    is_sme: bool
    issue_price: float
    open_: float
    high: float
    low: float
    close: float
    allotment_gain: float      # A: issue price -> listing open
    day_return: float          # B: listing open -> listing close
    best_exit: float           # B ceiling: open -> day's high (perfect timing)
    worst_drawdown: float      # B floor: open -> day's low
    next_day: float | None     # close -> next close


def _listing_bar(bars: pd.DataFrame, listing_date: str) -> int | None:
    """Index of the listing-day bar.

    Yahoo's first bar for a newly listed name is usually the listing day, but
    not always -- so match the date, and fall back to the first bar only when it
    is within a couple of days of the official date.
    """
    target = pd.Timestamp(listing_date)
    exact = bars.index.searchsorted(target)
    if exact < len(bars) and bars.index[exact].normalize() == target.normalize():
        return int(exact)
    if len(bars) and abs((bars.index[0] - target).days) <= 3:
        return 0
    return None


def measure(ipo: IPO, min_price: float = 5.0) -> ListingOutcome | None:
    if not ipo.listed or not ipo.issue_price:
        return None
    try:
        # A stock listed last week has ~5 bars. That is the whole point here.
        bars = load_prices(ipo.yf_symbol, start="2015-01-01", min_rows=1)
    except Exception as exc:
        log.debug("%s: no price data (%s)", ipo.symbol, exc)
        return None

    i = _listing_bar(bars, ipo.listing_date)
    if i is None:
        return None

    row = bars.iloc[i]
    o, h, l, c = (float(row["Open"]), float(row["High"]),
                  float(row["Low"]), float(row["Close"]))
    if min(o, h, l, c) < min_price:
        return None

    nxt = None
    if i + 1 < len(bars):
        nxt = float(bars["Close"].iloc[i + 1]) / c - 1.0

    return ListingOutcome(
        symbol=ipo.symbol, company=ipo.company, listing_date=ipo.listing_date,
        is_sme=ipo.is_sme, issue_price=ipo.issue_price,
        open_=o, high=h, low=l, close=c,
        allotment_gain=o / ipo.issue_price - 1.0,
        day_return=c / o - 1.0,
        best_exit=h / o - 1.0,
        worst_drawdown=l / o - 1.0,
        next_day=nxt,
    )


@dataclass
class StudySummary:
    segment: str
    n: int
    # Strategy A -- allotment
    allot_mean: float
    allot_median: float
    allot_win_rate: float
    # Strategy B -- buy at the listing open, sell at the close
    day_mean: float
    day_median: float
    day_win_rate: float
    day_sd: float
    day_t_stat: float
    # Risk and ceiling for B
    avg_best_exit: float
    avg_worst_dd: float
    worst_single_day: float
    p10_day: float
    # Costs
    breakeven_after_costs: float
    day_mean_net: float


def summarise(rows: list[ListingOutcome], segment: str,
              cost_pct: float = 0.0011) -> StudySummary:
    day = np.array([r.day_return for r in rows], dtype="float64")
    allot = np.array([r.allotment_gain for r in rows], dtype="float64")
    se = day.std(ddof=1) / np.sqrt(len(day)) if len(day) > 1 else float("nan")
    net = day - cost_pct
    return StudySummary(
        segment=segment, n=len(rows),
        allot_mean=float(allot.mean()), allot_median=float(np.median(allot)),
        allot_win_rate=float((allot > 0).mean()),
        day_mean=float(day.mean()), day_median=float(np.median(day)),
        day_win_rate=float((day > 0).mean()),
        day_sd=float(day.std(ddof=1)) if len(day) > 1 else float("nan"),
        day_t_stat=float(day.mean() / se) if se and se == se and se > 0 else float("nan"),
        avg_best_exit=float(np.mean([r.best_exit for r in rows])),
        avg_worst_dd=float(np.mean([r.worst_drawdown for r in rows])),
        worst_single_day=float(day.min()),
        p10_day=float(np.percentile(day, 10)),
        breakeven_after_costs=cost_pct,
        day_mean_net=float(net.mean()),
    )


def run_study(limit: int = 120, refresh: bool = False,
              cost_pct: float = 0.0011) -> dict:
    """Measure the most recent `limit` listed IPOs, split mainboard vs SME."""
    ipos = [i for i in past_issues(refresh) if i.listed][:limit]
    print(f" measuring {len(ipos)} listed IPOs (newest first)...")

    rows: list[ListingOutcome] = []
    for n, ipo in enumerate(ipos, 1):
        out = measure(ipo)
        if out:
            rows.append(out)
        if n % 25 == 0:
            print(f"   {n}/{len(ipos)} checked, {len(rows)} with usable data")

    if not rows:
        print(" no IPOs could be measured -- price data unavailable.")
        return {"summaries": [], "rows": []}

    summaries = [summarise(rows, "ALL", cost_pct)]
    main = [r for r in rows if not r.is_sme]
    sme = [r for r in rows if r.is_sme]
    if len(main) >= 5:
        summaries.append(summarise(main, "MAINBOARD", cost_pct))
    if len(sme) >= 5:
        summaries.append(summarise(sme, "SME", cost_pct))

    print_study(summaries, rows)
    return {"summaries": [s.__dict__ for s in summaries],
            "rows": [r.__dict__ for r in rows]}


def print_study(summaries: list[StudySummary], rows: list[ListingOutcome]) -> None:
    pct = lambda v: f"{v * 100:+.2f}%"                                # noqa: E731
    bar = "=" * 76

    print(f"\n{bar}")
    print(" IPO LISTING-DAY STUDY")
    print(bar)

    for s in summaries:
        print(f"\n-- {s.segment}  (n = {s.n}) {'-' * (52 - len(s.segment))}")
        print("\n  STRATEGY A -- allotment (issue price -> listing open)")
        print(f"    mean {pct(s.allot_mean):>9}   median {pct(s.allot_median):>9}"
              f"   positive {s.allot_win_rate * 100:.0f}% of the time")

        print("\n  STRATEGY B -- buy at the listing open, sell at the close")
        print(f"    mean {pct(s.day_mean):>9}   median {pct(s.day_median):>9}"
              f"   positive {s.day_win_rate * 100:.0f}% of the time")
        print(f"    net of costs {pct(s.day_mean_net):>9}"
              f"   t = {s.day_t_stat:>6.2f}   sd {s.day_sd * 100:.1f}%")
        print(f"    avg best exit {pct(s.avg_best_exit):>9} (perfect timing, unreachable)")
        print(f"    avg worst dip {pct(s.avg_worst_dd):>9}"
              f"   worst single day {pct(s.worst_single_day)}")
        print(f"    1 day in 10 is worse than {pct(s.p10_day)}")

        verdict = (
            "no edge -- t < 2, indistinguishable from luck"
            if not (s.day_t_stat == s.day_t_stat) or abs(s.day_t_stat) < 2
            else ("a real positive drift" if s.day_t_stat > 0
                  else "a real NEGATIVE drift -- buying the open loses money")
        )
        print(f"    -> {verdict}")

    print(f"\n{bar}")
    best = sorted(rows, key=lambda r: -r.day_return)[:3]
    worst = sorted(rows, key=lambda r: r.day_return)[:3]
    print(" Best listing days:  " + ", ".join(f"{r.symbol} {pct(r.day_return)}" for r in best))
    print(" Worst listing days: " + ", ".join(f"{r.symbol} {pct(r.day_return)}" for r in worst))
    print(bar + "\n")
