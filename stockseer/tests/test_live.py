"""Intraday integrity tests.

The opening-range test is the important one. Marking a 09:20 bar with the
09:15-09:30 range is the most common intraday backtest leak there is, it inflates
every downstream number, and it is invisible unless you check for it explicitly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockseer.live.intraday import atr, enrich, opening_range, relative_volume, vwap
from stockseer.live.ledger import Ledger, wilson_interval
from stockseer.live.monitor import _drop_forming_bar
from stockseer.live.rules import Rule, evaluate_rule


def _session(day: str, n: int = 75, start_price: float = 100.0, seed: int = 0):
    """One trading session of 5-minute bars, 09:15 to 15:30."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{day} 09:15", periods=n, freq="5min", tz="Asia/Kolkata")
    ret = rng.normal(0, 0.002, n)
    close = start_price * np.exp(np.cumsum(ret))
    high = close * (1 + np.abs(rng.normal(0, 0.001, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.001, n)))
    return pd.DataFrame(
        {"Open": close, "High": high, "Low": low, "Close": close,
         "Volume": rng.lognormal(10, 0.3, n)},
        index=idx,
    )


@pytest.fixture
def bars() -> pd.DataFrame:
    days = ["2026-08-03", "2026-08-04", "2026-08-05"]
    return pd.concat([_session(d, seed=i, start_price=100 + i)
                      for i, d in enumerate(days)])


# --------------------------------------------------------------------------- #
# No lookahead
# --------------------------------------------------------------------------- #
def test_opening_range_is_unknown_until_the_window_closes(bars):
    """Bars inside the first 15 minutes must carry no opening-range level."""
    orng = opening_range(bars, minutes=15)
    for _, day in bars.groupby(bars.index.date, sort=False):
        cutoff = day.index[0] + pd.Timedelta(minutes=15)
        early = orng.loc[day.index[day.index < cutoff]]
        assert early["or_high"].isna().all(), "opening range leaked before it existed"
        later = orng.loc[day.index[day.index >= cutoff]]
        assert later["or_high"].notna().all()


def test_opening_range_matches_the_actual_window(bars):
    orng = opening_range(bars, minutes=15)
    day = bars[bars.index.date == bars.index.date[0]]
    window = day.iloc[:3]                       # three 5-min bars = 15 minutes
    established = orng.loc[day.index[3]]
    assert established["or_high"] == pytest.approx(window["High"].max())
    assert established["or_low"] == pytest.approx(window["Low"].min())


def test_intraday_features_use_no_future_data(bars):
    """Truncating the frame must not change any already-computed row."""
    full = enrich(bars)
    cut = 150
    truncated = enrich(bars.iloc[:cut])
    cols = ["vwap", "atr", "rvol", "ema9", "ema21", "or_high"]
    pd.testing.assert_frame_equal(
        full[cols].iloc[cut - 1:cut], truncated[cols].iloc[-1:],
        check_names=False, rtol=1e-9,
    )


def test_vwap_resets_every_session(bars):
    vw = vwap(bars)
    for _, day in bars.groupby(bars.index.date, sort=False):
        first = day.index[0]
        tp = (day["High"].iloc[0] + day["Low"].iloc[0] + day["Close"].iloc[0]) / 3
        # The session's first bar has only itself in the average.
        assert vw.loc[first] == pytest.approx(tp)


def test_atr_does_not_span_the_overnight_gap():
    """A big gap between sessions must not register as a huge true range."""
    a = _session("2026-08-03", n=40, start_price=100.0, seed=1)
    b = _session("2026-08-04", n=40, start_price=200.0, seed=2)   # 100% gap
    joined = pd.concat([a, b])
    tr_max = atr(joined, period=2).max()
    assert tr_max < 20.0, "overnight gap leaked into intraday ATR"


def test_drop_forming_bar_removes_only_an_incomplete_bar():
    now = pd.Timestamp.now(tz="Asia/Kolkata").floor("5min")
    idx = pd.date_range(end=now, periods=5, freq="5min", tz="Asia/Kolkata")
    df = pd.DataFrame({"Close": range(5)}, index=idx)
    assert len(_drop_forming_bar(df, 5)) == 4        # last bar still forming

    old = df.copy()
    old.index = old.index - pd.Timedelta(hours=2)
    assert len(_drop_forming_bar(old, 5)) == 5       # all settled


# --------------------------------------------------------------------------- #
# Barrier evaluation
# --------------------------------------------------------------------------- #
def _flat_bars(closes: list[float], highs=None, lows=None) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2026-08-03 09:15", periods=n, freq="5min", tz="Asia/Kolkata")
    df = pd.DataFrame({
        "Open": closes,
        "High": highs or [c * 1.0005 for c in closes],
        "Low": lows or [c * 0.9995 for c in closes],
        "Close": closes,
        "Volume": [1000.0] * n,
    }, index=idx)
    df["atr"] = 1.0
    df["mins_open"] = np.arange(n) * 5
    return df


def test_target_before_stop_scores_a_win():
    closes = [100.0] * 20 + [102.0] * 10
    bars = _flat_bars(closes)
    rule = Rule("t", lambda b: pd.Series(b.index == b.index[19], index=b.index))
    st = evaluate_rule(bars, rule, stop_atr=1.0, target_atr=1.5, cost_r=0.0)
    assert st.n_signals == 1
    assert st.hit_rate == pytest.approx(1.0)
    assert st.expectancy_r == pytest.approx(1.5)


def test_stop_before_target_scores_a_loss():
    closes = [100.0] * 20 + [98.0] * 10
    bars = _flat_bars(closes)
    rule = Rule("t", lambda b: pd.Series(b.index == b.index[19], index=b.index))
    st = evaluate_rule(bars, rule, stop_atr=1.0, target_atr=1.5, cost_r=0.0)
    assert st.stop_rate == pytest.approx(1.0)
    assert st.expectancy_r == pytest.approx(-1.0)


def test_both_barriers_in_one_bar_assumes_the_stop_filled():
    """Without tick data the order is unknowable; assume the worse case.

    The opposite assumption silently converts losers into winners and is a
    common source of intraday backtests that cannot be reproduced live.
    """
    closes = [100.0] * 20 + [100.0]
    bars = _flat_bars(closes, highs=[100.05] * 20 + [102.0], lows=[99.95] * 20 + [98.0])
    rule = Rule("t", lambda b: pd.Series(b.index == b.index[19], index=b.index))
    st = evaluate_rule(bars, rule, stop_atr=1.0, target_atr=1.5, cost_r=0.0)
    assert st.expectancy_r == pytest.approx(-1.0)


def test_positions_never_carry_overnight():
    """A signal late in the session is closed at the session's end, not the next day."""
    day1 = _flat_bars([100.0] * 5)
    day2 = _flat_bars([130.0] * 5)
    day2.index = day2.index + pd.Timedelta(days=1)
    bars = pd.concat([day1, day2])
    rule = Rule("t", lambda b: pd.Series(b.index == b.index[4], index=b.index))
    st = evaluate_rule(bars, rule, stop_atr=1.0, target_atr=1.5, cost_r=0.0)
    # The 30-point overnight gap must not be booked as a 1.5R win.
    assert st.expectancy_r < 1.0


def test_costs_reduce_expectancy():
    closes = [100.0] * 20 + [102.0] * 10
    bars = _flat_bars(closes)
    rule = Rule("t", lambda b: pd.Series(b.index == b.index[19], index=b.index))
    free = evaluate_rule(bars, rule, cost_r=0.0).expectancy_r
    paid = evaluate_rule(bars, rule, cost_r=0.1).expectancy_r
    assert paid == pytest.approx(free - 0.1)


def test_rule_that_never_fires_reports_zero_not_a_crash():
    bars = _flat_bars([100.0] * 30)
    rule = Rule("never", lambda b: pd.Series(False, index=b.index))
    st = evaluate_rule(bars, rule)
    assert st.n_signals == 0
    assert not st.worth_trading


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #
def test_ledger_round_trip(tmp_path):
    led = Ledger(tmp_path / "j.json", capital=40_000)
    t = led.open_trade("RELIANCE.NS", "vwap_reclaim", "long", 1400.0, 1385.0, 1425.0, 28)
    assert t.is_open and led.stats().n_open == 1

    led.close_trade(t.id, 1425.0, "target")
    st = led.stats()
    assert st.n_closed == 1 and st.wins == 1
    assert t.pnl() > 0
    assert t.costs > 0, "paper trades must still be charged real costs"

    reloaded = Ledger(tmp_path / "j.json")
    assert len(reloaded.trades) == 1


def test_r_multiple_is_measured_against_intended_risk(tmp_path):
    led = Ledger(tmp_path / "j.json")
    t = led.open_trade("X", "r", "long", entry=100.0, stop=90.0, target=120.0, qty=10)
    led.close_trade(t.id, 120.0, "target")
    assert t.r_multiple() == pytest.approx(2.0, abs=0.05)   # 20 gained / 10 risked


def test_wilson_interval_is_wide_when_the_sample_is_small():
    lo_small, hi_small = wilson_interval(6, 10)
    lo_big, hi_big = wilson_interval(600, 1000)
    assert (hi_small - lo_small) > (hi_big - lo_big) * 5
    assert lo_small < 0.42 < hi_small, "10 trades cannot resolve a 60% win rate"
    assert lo_big > 0.42


def test_wilson_handles_the_degenerate_cases():
    assert wilson_interval(0, 0) == (pytest.approx(float("nan"), nan_ok=True),) * 2 \
        or np.isnan(wilson_interval(0, 0)[0])
    lo, hi = wilson_interval(0, 20)
    assert lo == 0.0 and 0 < hi < 0.3
