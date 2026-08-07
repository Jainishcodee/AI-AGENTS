"""Alert rules, and the machinery that measures whether they are worth anything.

Every rule here is a boolean over enriched intraday bars. None of them is assumed
to work: :func:`evaluate_rule` runs each one through a triple-barrier test on real
history and reports the hit rate, the payoff, and the expectancy. A rule that does
not clear its break-even win rate should not fire, however good the story is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from .intraday import enrich

# A rule maps enriched bars to a boolean Series: True where it fires.
RuleFn = Callable[[pd.DataFrame], pd.Series]


@dataclass(frozen=True)
class Rule:
    name: str
    fn: RuleFn
    side: str = "long"
    description: str = ""

    def fires(self, bars: pd.DataFrame) -> pd.Series:
        return self.fn(bars).fillna(False).astype(bool)


@dataclass
class Signal:
    rule: str
    symbol: str
    side: str
    at: pd.Timestamp
    price: float
    stop: float
    target: float
    atr: float
    reason: str
    stats: dict[str, float] = field(default_factory=dict)

    @property
    def rr(self) -> float:
        risk = abs(self.price - self.stop)
        return abs(self.target - self.price) / risk if risk else float("nan")


# --------------------------------------------------------------------------- #
# The rules
# --------------------------------------------------------------------------- #
def _crossed_up(series: pd.Series, level: pd.Series) -> pd.Series:
    """True on the bar where series moves from at-or-below to above `level`."""
    return (series > level) & (series.shift(1) <= level.shift(1))


def opening_range_break(bars: pd.DataFrame, rvol_min: float = 1.5) -> pd.Series:
    """Price breaks above the opening range on above-average volume.

    The volume filter is doing real work: opening-range breaks on thin volume are
    predominantly noise, and trading every break is how the pattern got its
    reputation for not working.
    """
    return (
        _crossed_up(bars["Close"], bars["or_high"])
        & (bars["rvol"] >= rvol_min)
        & (bars["mins_open"] <= 120)
    )


def vwap_reclaim(bars: pd.DataFrame, rvol_min: float = 1.2) -> pd.Series:
    """Price crosses back above VWAP after trading below it, on volume."""
    below_recently = (~bars["above_vwap"]).rolling(6).sum() >= 3
    return (
        _crossed_up(bars["Close"], bars["vwap"])
        & below_recently
        & (bars["rvol"] >= rvol_min)
    )


def volume_surge_breakout(bars: pd.DataFrame, rvol_min: float = 3.0) -> pd.Series:
    """A volume spike with the bar closing in the top of its own range."""
    rng = (bars["High"] - bars["Low"]).replace(0.0, np.nan)
    close_loc = (bars["Close"] - bars["Low"]) / rng
    return (bars["rvol"] >= rvol_min) & (close_loc >= 0.7) & (bars["Close"] > bars["vwap"])


def ema_pullback(bars: pd.DataFrame) -> pd.Series:
    """Uptrend, pull back to the fast EMA, then resume."""
    trend = bars["ema9"] > bars["ema21"]
    touched = bars["Low"].rolling(3).min() <= bars["ema9"]
    return trend & touched & _crossed_up(bars["Close"], bars["ema9"]) & (bars["Close"] > bars["vwap"])


def vwap_rejection_short(bars: pd.DataFrame, rvol_min: float = 1.2) -> pd.Series:
    """Mirror of the reclaim: failure at VWAP from below, for a short."""
    above_recently = bars["above_vwap"].rolling(6).sum() >= 3
    crossed_down = (bars["Close"] < bars["vwap"]) & (bars["Close"].shift(1) >= bars["vwap"].shift(1))
    return crossed_down & above_recently & (bars["rvol"] >= rvol_min)


REGISTRY: list[Rule] = [
    Rule("orb_15", lambda b: opening_range_break(b), "long",
         "15-min opening range break on 1.5x volume"),
    Rule("vwap_reclaim", lambda b: vwap_reclaim(b), "long",
         "reclaims VWAP from below on 1.2x volume"),
    Rule("volume_surge", lambda b: volume_surge_breakout(b), "long",
         "3x volume bar closing strong above VWAP"),
    Rule("ema_pullback", lambda b: ema_pullback(b), "long",
         "9/21 uptrend, pullback to EMA9, resumes"),
    Rule("vwap_reject", lambda b: vwap_rejection_short(b), "short",
         "loses VWAP from above on volume"),
]


# --------------------------------------------------------------------------- #
# Measuring a rule
# --------------------------------------------------------------------------- #
@dataclass
class RuleStats:
    rule: str
    side: str
    n_signals: float
    hit_rate: float          # share reaching target before stop
    stop_rate: float
    timeout_rate: float
    avg_r: float             # mean outcome in units of risk
    expectancy_r: float
    breakeven_win_rate: float
    median_bars_held: float
    n_sessions: float

    @property
    def worth_trading(self) -> bool:
        return self.expectancy_r > 0 and self.n_signals >= 30


def evaluate_rule(
    bars: pd.DataFrame,
    rule: Rule,
    stop_atr: float = 1.0,
    target_atr: float = 1.5,
    max_bars: int = 24,
    cost_r: float = 0.05,
) -> RuleStats:
    """Triple-barrier test: for each signal, which comes first -- target or stop?

    This is the only honest way to score an intraday rule. Measuring "average
    return N bars later" hides the path: a trade that goes to -3R before closing
    at +0.5R is scored a winner by that method, and would have been stopped out
    in reality. Here the barriers are walked bar by bar, in order.

    ``max_bars`` acts as the time barrier -- an intraday position is closed by the
    session's end whether or not either level was touched.
    """
    fires = rule.fires(bars)
    idx = np.flatnonzero(fires.to_numpy())
    if idx.size == 0:
        return RuleStats(rule.name, rule.side, 0.0, *(float("nan"),) * 7, 0.0)

    high = bars["High"].to_numpy()
    low = bars["Low"].to_numpy()
    close = bars["Close"].to_numpy()
    atr_v = bars["atr"].to_numpy()
    sessions = pd.Series(bars.index.date, index=bars.index).to_numpy()
    long = rule.side == "long"

    outcomes, held = [], []
    for i in idx:
        a = atr_v[i]
        if not np.isfinite(a) or a <= 0:
            continue
        entry = close[i]
        risk = stop_atr * a
        stop = entry - risk if long else entry + risk
        target = entry + target_atr * a if long else entry - target_atr * a

        result, bars_held = None, 0
        for j in range(i + 1, min(i + 1 + max_bars, len(close))):
            if sessions[j] != sessions[i]:
                break  # intraday only: never carry a position overnight
            bars_held = j - i
            hit_stop = low[j] <= stop if long else high[j] >= stop
            hit_target = high[j] >= target if long else low[j] <= target
            # Both touched inside one bar: assume the stop filled first. Without
            # tick data you cannot know the order, and the pessimistic
            # assumption is the only one that will not flatter the result.
            if hit_stop:
                result = -1.0
                break
            if hit_target:
                result = target_atr / stop_atr
                break
        if result is None:
            j = min(i + bars_held, len(close) - 1)
            result = ((close[j] - entry) if long else (entry - close[j])) / risk
        outcomes.append(result - cost_r)
        held.append(max(bars_held, 1))

    if not outcomes:
        return RuleStats(rule.name, rule.side, 0.0, *(float("nan"),) * 7, 0.0)

    arr = np.asarray(outcomes, dtype="float64")
    rr = target_atr / stop_atr
    wins = arr > 0
    return RuleStats(
        rule=rule.name,
        side=rule.side,
        n_signals=float(arr.size),
        hit_rate=float((arr >= rr - cost_r - 1e-9).mean()),
        stop_rate=float((arr <= -1.0 + 1e-9).mean()),
        timeout_rate=float(((arr > -1.0 + 1e-9) & (arr < rr - cost_r - 1e-9)).mean()),
        avg_r=float(arr.mean()),
        expectancy_r=float(arr.mean()),
        breakeven_win_rate=float((1.0 + cost_r) / (1.0 + rr)),
        median_bars_held=float(np.median(held)),
        n_sessions=float(len(np.unique(sessions))),
        )


def evaluate_all(
    raw_bars: pd.DataFrame, rules: list[Rule] | None = None, **kwargs
) -> list[RuleStats]:
    bars = enrich(raw_bars)
    return [evaluate_rule(bars, r, **kwargs) for r in (rules or REGISTRY)]


def live_signals(
    raw_bars: pd.DataFrame,
    symbol: str,
    rules: list[Rule] | None = None,
    stop_atr: float = 1.0,
    target_atr: float = 1.5,
    stats: dict[str, RuleStats] | None = None,
) -> list[Signal]:
    """Signals firing on the most recent completed bar only."""
    bars = enrich(raw_bars)
    if bars.empty:
        return []
    last = bars.iloc[-1]
    a = float(last.get("atr", float("nan")))
    if not np.isfinite(a) or a <= 0:
        return []

    out = []
    for rule in rules or REGISTRY:
        fired = rule.fires(bars)
        if not bool(fired.iloc[-1]):
            continue
        long = rule.side == "long"
        price = float(last["Close"])
        st = (stats or {}).get(rule.name)
        out.append(Signal(
            rule=rule.name,
            symbol=symbol,
            side=rule.side,
            at=bars.index[-1],
            price=price,
            stop=price - stop_atr * a if long else price + stop_atr * a,
            target=price + target_atr * a if long else price - target_atr * a,
            atr=a,
            reason=rule.description,
            stats={
                "hit_rate": st.hit_rate if st else float("nan"),
                "expectancy_r": st.expectancy_r if st else float("nan"),
                "n_signals": st.n_signals if st else 0.0,
            },
        ))
    return out
