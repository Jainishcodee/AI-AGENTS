"""Tests for the advisory scorer.

The fill-timing test is the one that matters. Scoring a call from the day's low,
or from any bar before publication, turns every service into a genius.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockseer.live.advisors import Call, CallLog, score_calls


@pytest.fixture
def bars() -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=400)
    rng = np.random.default_rng(5)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, len(idx))))
    return pd.DataFrame({
        "Open": close, "High": close * 1.01, "Low": close * 0.99,
        "Close": close, "Volume": 1e6,
    }, index=idx)


def _loader(bars):
    return lambda symbol: bars


# --------------------------------------------------------------------------- #
def test_fill_happens_at_or_after_publication(bars):
    """You cannot buy before the call was made."""
    pub = bars.index[100]
    call = Call("svc", "X", "long", str(pub.date()), horizon_days=5)
    outcomes, _ = score_calls([call], _loader(bars), cost_pct=0.0)
    assert len(outcomes) == 1
    assert pd.Timestamp(outcomes[0].filled_at) >= pub
    assert outcomes[0].fill_price == pytest.approx(float(bars["Close"].iloc[100]))


def test_explicit_target_is_honoured(bars):
    entry = float(bars["Close"].iloc[50])
    call = Call("svc", "X", "long", str(bars.index[50].date()),
                entry=entry, stop=entry * 0.5, target=entry * 1.001, horizon_days=20)
    outcomes, _ = score_calls([call], _loader(bars), cost_pct=0.0)
    assert outcomes[0].result == "target"
    assert outcomes[0].pct_return > 0


def test_stop_is_honoured(bars):
    entry = float(bars["Close"].iloc[50])
    call = Call("svc", "X", "long", str(bars.index[50].date()),
                entry=entry, stop=entry * 0.999, target=entry * 2.0, horizon_days=20)
    outcomes, _ = score_calls([call], _loader(bars), cost_pct=0.0)
    assert outcomes[0].result == "stop"
    assert outcomes[0].pct_return < 0


def test_timeout_closes_at_the_horizon(bars):
    entry = float(bars["Close"].iloc[50])
    call = Call("svc", "X", "long", str(bars.index[50].date()),
                entry=entry, stop=entry * 0.1, target=entry * 10.0, horizon_days=7)
    outcomes, _ = score_calls([call], _loader(bars), cost_pct=0.0)
    assert outcomes[0].result == "timeout"
    assert outcomes[0].bars_held <= 7


def test_costs_reduce_the_measured_return(bars):
    call = Call("svc", "X", "long", str(bars.index[50].date()), horizon_days=5)
    free, _ = score_calls([call], _loader(bars), cost_pct=0.0)
    paid, _ = score_calls([call], _loader(bars), cost_pct=0.01)
    assert paid[0].pct_return == pytest.approx(free[0].pct_return - 0.01)


def test_random_calls_show_no_edge_over_the_baseline(bars):
    """A source picking dates at random must not register an edge."""
    rng = np.random.default_rng(9)
    calls = [
        Call("noise", "X", "long", str(bars.index[i].date()), horizon_days=10)
        for i in rng.choice(350, 120, replace=False)
    ]
    _, stats = score_calls(calls, _loader(bars), cost_pct=0.0)
    assert abs(stats["noise"].edge_t_stat) < 2.0


def test_a_source_that_peeks_at_the_future_is_detected(bars):
    """The scorer must catch a genuine edge when one is present.

    A test that only proves it rejects noise would pass on a scorer that
    rejects everything.
    """
    fwd = bars["Close"].shift(-10) / bars["Close"] - 1.0
    winners = [i for i in range(350) if fwd.iloc[i] > 0.02]
    calls = [
        Call("cheater", "X", "long", str(bars.index[i].date()), horizon_days=10)
        for i in winners[:120]
    ]
    _, stats = score_calls(calls, _loader(bars), cost_pct=0.0)
    assert stats["cheater"].edge_t_stat > 2.0
    assert stats["cheater"].edge_vs_baseline > 0


def test_baseline_is_computed_from_the_same_symbol(bars):
    calls = [Call("s", "X", "long", str(bars.index[i].date()), horizon_days=10)
             for i in range(50, 100)]
    _, stats = score_calls(calls, _loader(bars), cost_pct=0.0)
    st = stats["s"]
    assert st.baseline_avg_pct == st.baseline_avg_pct   # not NaN
    assert st.edge_vs_baseline == pytest.approx(st.avg_pct - st.baseline_avg_pct)


def test_calls_needed_scales_with_the_noise(bars):
    """A weak edge must demand more evidence than a strong one."""
    fwd = bars["Close"].shift(-10) / bars["Close"] - 1.0
    strong = [Call("strong", "X", "long", str(bars.index[i].date()), horizon_days=10)
              for i in range(350) if fwd.iloc[i] > 0.03][:100]
    rng = np.random.default_rng(4)
    weak = [Call("weak", "X", "long", str(bars.index[i].date()), horizon_days=10)
            for i in rng.choice(350, 100, replace=False)]
    _, s1 = score_calls(strong, _loader(bars), cost_pct=0.0)
    _, s2 = score_calls(weak, _loader(bars), cost_pct=0.0)
    if s2["weak"].calls_needed == s2["weak"].calls_needed:   # positive but weak
        assert s1["strong"].calls_needed < s2["weak"].calls_needed


def test_calls_published_past_the_data_are_skipped(bars):
    call = Call("svc", "X", "long", "2099-01-01", horizon_days=5)
    outcomes, stats = score_calls([call], _loader(bars))
    assert outcomes == [] and stats == {}


def test_call_log_persists(tmp_path):
    log = CallLog(tmp_path / "c.json")
    log.add(Call("svc", "RELIANCE.NS", "long", "2026-06-02"))
    log.add(Call("other", "TCS.NS", "long", "2026-06-03"))
    assert CallLog(tmp_path / "c.json").sources() == ["other", "svc"]


def test_csv_import(tmp_path):
    csv_path = tmp_path / "in.csv"
    csv_path.write_text(
        "symbol,side,published_at,target\nRELIANCE.NS,long,2026-06-02,1500\n",
        encoding="utf-8",
    )
    log = CallLog(tmp_path / "c.json")
    assert log.import_csv(csv_path, source="svc") == 1
    assert log.calls[0].target == 1500.0
    assert log.calls[0].source == "svc"
