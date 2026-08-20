"""Cross-sectional screen for large forward moves, and a test of whether it works.

"Find me the next Cupid" is a testable question, so it should be tested rather
than answered with a story. The method:

  1. Rewind to a date in the past.
  2. Score every stock on what was knowable *then* -- momentum, trend,
     distance from its high, volatility, liquidity.
  3. Look forward a year and count how many doubled.
  4. Compare the screened group against the whole universe.

If the screen has no edge, the two rates match and the screen is decoration.

**Survivorship bias is the wound this method cannot fully heal.** Yahoo serves
data for stocks that still trade. Companies that collapsed and delisted have
quietly left the sample, so every hit rate below is optimistic -- the real
downside is worse than measured. Treated as an upper bound, not a forecast.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .data import load_prices, load_prices_live

log = logging.getLogger(__name__)


@dataclass
class Snapshot:
    """What was knowable about one stock on one date."""

    symbol: str
    date: pd.Timestamp
    price: float
    mom_6m: float
    mom_12m: float
    above_200d: float          # % above the 200-day average
    pct_of_52w_high: float     # 1.0 = sitting at the high
    vol_ann: float
    turnover_cr: float         # median daily traded value, Rs crore
    forward_1y: float = float("nan")


def snapshot(bars: pd.DataFrame, symbol: str, asof: pd.Timestamp,
             forward_days: int = 252) -> Snapshot | None:
    """Score one stock as of `asof`, using only bars up to that date."""
    hist = bars[bars.index <= asof]
    if len(hist) < 260:
        return None

    c = hist["Close"]
    price = float(c.iloc[-1])
    if price <= 5:
        return None

    ret = c.pct_change()
    sma200 = float(c.rolling(200).mean().iloc[-1])
    hi52 = float(c.tail(252).max())
    turnover = float((c * hist["Volume"]).tail(60).median() / 1e7)

    fwd = float("nan")
    future = bars[bars.index > asof]
    if len(future) >= forward_days:
        fwd = float(future["Close"].iloc[forward_days - 1]) / price - 1.0

    return Snapshot(
        symbol=symbol, date=asof, price=price,
        mom_6m=float(c.iloc[-1] / c.iloc[-127] - 1.0) if len(c) > 127 else float("nan"),
        mom_12m=float(c.iloc[-1] / c.iloc[-253] - 1.0) if len(c) > 253 else float("nan"),
        above_200d=price / sma200 - 1.0 if sma200 > 0 else float("nan"),
        pct_of_52w_high=price / hi52 if hi52 > 0 else float("nan"),
        vol_ann=float(ret.tail(252).std() * np.sqrt(252)),
        turnover_cr=turnover,
        forward_1y=fwd,
    )


@dataclass
class ScreenRule:
    """The conditions a candidate must satisfy."""

    min_mom_6m: float = 0.30
    min_mom_12m: float = 0.50
    min_above_200d: float = 0.10
    min_pct_of_high: float = 0.90      # near its 52-week high, not recovering
    min_turnover_cr: float = 0.5       # tradable without moving the price
    max_vol: float = 1.50              # exclude the truly unhinged
    name: str = "momentum-breakout"

    def passes(self, s: Snapshot) -> bool:
        vals = (s.mom_6m, s.mom_12m, s.above_200d, s.pct_of_52w_high, s.vol_ann)
        if any(v != v for v in vals):
            return False
        return (
            s.mom_6m >= self.min_mom_6m
            and s.mom_12m >= self.min_mom_12m
            and s.above_200d >= self.min_above_200d
            and s.pct_of_52w_high >= self.min_pct_of_high
            and s.turnover_cr >= self.min_turnover_cr
            and s.vol_ann <= self.max_vol
        )


@dataclass
class ScreenResult:
    rule: str
    asof: str
    n_universe: int
    n_passed: int
    base_double: float          # P(2x in a year) across the universe
    screen_double: float        # P(2x | passed the screen)
    base_mean: float
    screen_mean: float
    base_loss50: float          # P(halving) across the universe
    screen_loss50: float
    t_stat: float
    lift: float
    passed: list[Snapshot] = field(default_factory=list)


def evaluate(snaps: list[Snapshot], rule: ScreenRule, asof: str) -> ScreenResult:
    scored = [s for s in snaps if s.forward_1y == s.forward_1y]
    if not scored:
        raise ValueError("no snapshots have a forward return yet")

    hits = [s for s in scored if rule.passes(s)]
    all_f = np.array([s.forward_1y for s in scored])
    hit_f = np.array([s.forward_1y for s in hits]) if hits else np.array([])

    if hit_f.size > 1:
        se = np.sqrt(all_f.var(ddof=1) / hit_f.size)
        t = float((hit_f.mean() - all_f.mean()) / se) if se > 0 else float("nan")
    else:
        t = float("nan")

    base_d = float((all_f >= 1.0).mean())
    scr_d = float((hit_f >= 1.0).mean()) if hit_f.size else float("nan")

    return ScreenResult(
        rule=rule.name, asof=asof,
        n_universe=len(scored), n_passed=len(hits),
        base_double=base_d, screen_double=scr_d,
        base_mean=float(all_f.mean()),
        screen_mean=float(hit_f.mean()) if hit_f.size else float("nan"),
        base_loss50=float((all_f <= -0.5).mean()),
        screen_loss50=float((hit_f <= -0.5).mean()) if hit_f.size else float("nan"),
        t_stat=t,
        lift=scr_d / base_d if base_d > 0 else float("nan"),
        passed=hits,
    )


def load_universe(symbols: list[str], start: str = "2015-01-01",
                  quiet: bool = True) -> dict[str, pd.DataFrame]:
    """Fetch daily bars for a list of symbols, skipping whatever fails."""
    out: dict[str, pd.DataFrame] = {}
    for n, sym in enumerate(symbols, 1):
        try:
            out[sym] = load_prices(sym, start=start, min_rows=300)
        except Exception as exc:
            log.debug("%s skipped (%s)", sym, exc)
        if not quiet and n % 50 == 0:
            print(f"   {n}/{len(symbols)} fetched, {len(out)} usable")
    return out


def run_screen(bars: dict[str, pd.DataFrame], asof: pd.Timestamp,
               rule: ScreenRule, forward_days: int = 252) -> ScreenResult:
    snaps = []
    for sym, df in bars.items():
        s = snapshot(df, sym, asof, forward_days)
        if s:
            snaps.append(s)
    return evaluate(snaps, rule, str(asof.date()))


def print_result(r: ScreenResult, show: int = 12) -> None:
    pct = lambda v: "   n/a" if v != v else f"{v * 100:5.1f}%"     # noqa: E731
    print(f"\n  as of {r.asof}   universe {r.n_universe}   passed {r.n_passed}")
    if r.n_passed == 0:
        print("    nothing passed the screen on this date.")
        return
    print(f"    {'':<22}{'screened':>10}{'everything':>12}")
    print(f"    {'doubled in 1y':<22}{pct(r.screen_double):>10}{pct(r.base_double):>12}")
    print(f"    {'halved in 1y':<22}{pct(r.screen_loss50):>10}{pct(r.base_loss50):>12}")
    print(f"    {'mean 1y return':<22}{pct(r.screen_mean):>10}{pct(r.base_mean):>12}")
    print(f"    lift {r.lift:.2f}x    t = {r.t_stat:.2f}")
