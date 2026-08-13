"""The listing-morning test, minute by minute.

The daily-bar study could only measure open -> close and showed no edge. But the
actual claim is narrower: *buy at 10:00, sell around 11:00.* Average best-exit
was +5.6%, so intraday upside plainly exists -- the question is whether it lands
in that specific window, or whether it is scattered randomly through the day (in
which case there is nothing to time).

Mainboard IPOs open at 10:00 IST after a 09:00-10:00 special pre-open call
auction, so the first traded minute *is* the entry this strategy describes.

Requires real 1-minute data, which is what the Angel One historical key unlocks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import time

import numpy as np
import pandas as pd

from .registry import IPO

log = logging.getLogger(__name__)

# Checkpoints through the listing morning, in IST.
CHECKPOINTS = [time(10, 15), time(10, 30), time(10, 45), time(11, 0),
               time(11, 30), time(12, 0), time(13, 0), time(15, 20)]


@dataclass
class MorningPath:
    symbol: str
    listing_date: str
    is_sme: bool
    entry: float                     # first traded price of the session
    at: dict[str, float]             # "11:00" -> return from entry
    mfe_to_11: float                 # best unrealised gain before 11:00
    mae_to_11: float                 # worst unrealised loss before 11:00
    peak_minute: str                 # when the session high actually happened
    first_minute: str                # session start; SME names open at 09:15
    n_bars: int


def _session_bars(bars: pd.DataFrame, listing_date: str) -> pd.DataFrame:
    day = pd.Timestamp(listing_date).date()
    same = bars[bars.index.date == day]
    return same.sort_index()


def measure_morning(bars: pd.DataFrame, ipo: IPO) -> MorningPath | None:
    """Track one listing session from its first traded minute."""
    day = _session_bars(bars, ipo.listing_date)
    if len(day) < 20:
        return None

    entry = float(day["Open"].iloc[0])
    if entry <= 0:
        return None

    at: dict[str, float] = {}
    for cp in CHECKPOINTS:
        upto = day[day.index.time <= cp]
        if upto.empty:
            continue
        at[cp.strftime("%H:%M")] = float(upto["Close"].iloc[-1]) / entry - 1.0

    before_11 = day[day.index.time <= time(11, 0)]
    if before_11.empty:
        return None

    peak_idx = day["High"].idxmax()
    return MorningPath(
        symbol=ipo.symbol,
        listing_date=ipo.listing_date,
        is_sme=ipo.is_sme,
        entry=entry,
        at=at,
        mfe_to_11=float(before_11["High"].max()) / entry - 1.0,
        mae_to_11=float(before_11["Low"].min()) / entry - 1.0,
        peak_minute=peak_idx.strftime("%H:%M"),
        first_minute=day.index[0].strftime("%H:%M"),
        n_bars=len(day),
    )


def run_intraday_study(feed, ipos: list[IPO], interval: str = "1m",
                       days_back: int = 28, cost_pct: float = 0.0011) -> dict:
    """Measure the listing morning for every IPO we can still get bars for."""
    paths: list[MorningPath] = []
    for ipo in ipos:
        try:
            bars = feed.history(ipo.yf_symbol.replace(".NS", ""), interval, days_back)
        except Exception as exc:
            log.info("%s: no intraday data (%s)", ipo.symbol, exc)
            continue
        p = measure_morning(bars, ipo)
        if p:
            paths.append(p)
            print(f"   {ipo.symbol:<14}{ipo.listing_date}  entry {p.entry:>9.2f}  "
                  f"11:00 {p.at.get('11:00', float('nan')) * 100:>+7.2f}%  "
                  f"peak at {p.peak_minute}")

    if not paths:
        print("\n No listing-day intraday data available for these IPOs.")
        return {"paths": [], "summary": {}}

    print_intraday(paths, cost_pct)
    return {"paths": [p.__dict__ for p in paths],
            "summary": summarise_morning(paths, cost_pct)}


def summarise_morning(paths: list[MorningPath], cost_pct: float = 0.0011) -> dict:
    out: dict[str, dict] = {}
    for cp in CHECKPOINTS:
        k = cp.strftime("%H:%M")
        vals = np.array([p.at[k] for p in paths if k in p.at], dtype="float64")
        if vals.size < 3:
            continue
        net = vals - cost_pct
        se = vals.std(ddof=1) / np.sqrt(vals.size) if vals.size > 1 else float("nan")
        out[k] = {
            "n": int(vals.size),
            "mean": float(vals.mean()),
            "median": float(np.median(vals)),
            "win_rate": float((vals > cost_pct).mean()),
            "mean_net": float(net.mean()),
            "t_stat": float(vals.mean() / se) if se and se == se and se > 0 else float("nan"),
        }
    return out


def print_intraday(paths: list[MorningPath], cost_pct: float = 0.0011) -> None:
    summary = summarise_morning(paths, cost_pct)
    bar = "=" * 74
    print(f"\n{bar}")
    print(f" IPO LISTING-MORNING PATH   (n = {len(paths)} listings)")
    print(bar)
    print("\n Holding from the first traded minute until:")
    print(f"   {'exit':<8}{'n':>4}{'mean':>10}{'median':>10}{'win%':>8}"
          f"{'net':>10}{'t':>7}")
    print("   " + "-" * 55)
    for k, s in summary.items():
        print(f"   {k:<8}{s['n']:>4}{s['mean'] * 100:>9.2f}%{s['median'] * 100:>9.2f}%"
              f"{s['win_rate'] * 100:>7.0f}%{s['mean_net'] * 100:>9.2f}%{s['t_stat']:>7.2f}")

    mfe = np.array([p.mfe_to_11 for p in paths])
    mae = np.array([p.mae_to_11 for p in paths])
    print(f"\n Before 11:00, on average:")
    print(f"   best unrealised gain  {mfe.mean() * 100:>+6.2f}%   "
          f"(the ceiling if you timed the exit perfectly)")
    print(f"   worst unrealised loss {mae.mean() * 100:>+6.2f}%   "
          f"(what you sit through to get it)")

    # "Peaked before 11:00" conflates two opposite outcomes. Peaking in the very
    # first minute means it opened at its high and faded -- you never had a gain
    # to take. Only a peak strictly after the open is the pattern being claimed.
    n = len(paths)
    opens = [p for p in paths if p.peak_minute <= p.first_minute]
    window = [p for p in paths
              if p.first_minute < p.peak_minute <= "11:00"]
    later = [p for p in paths if p.peak_minute > "11:00"]

    print("\n When did the session high actually happen?")
    print(f"   in the opening minute (opened high, faded) : {len(opens):>3}"
          f"  ({len(opens) / n * 100:>3.0f}%)  <- no gain to take")
    print(f"   after the open but before 11:00            : {len(window):>3}"
          f"  ({len(window) / n * 100:>3.0f}%)  <- the claimed pattern")
    print(f"   after 11:00                                : {len(later):>3}"
          f"  ({len(later) / n * 100:>3.0f}%)  <- exiting at 11 sells too early")

    k = "11:00"
    if k in summary:
        s = summary[k]
        verdict = ("a real edge" if s["t_stat"] > 2 else
                   "a real NEGATIVE drift" if s["t_stat"] < -2 else
                   "no edge -- indistinguishable from luck")
        print(f"\n VERDICT at 11:00: {verdict} "
              f"(t = {s['t_stat']:.2f}, n = {s['n']})")
        if s["n"] < 30:
            print(f"   Note: {s['n']} listings is a small sample. Treat as indicative,"
                  f"\n   and re-run as more IPOs list -- the registry updates itself.")
    print(f"{bar}\n")
