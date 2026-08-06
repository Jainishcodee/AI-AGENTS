"""The tests that matter: no lookahead, correct label alignment, purged splits.

Everything else in a stock-prediction project is tuning. These four properties
are the difference between a backtest and a story.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockseer.backtest import build_positions, performance_stats, simulate
from stockseer.features import build_features
from stockseer.labels import align, forward_return, make_label
from stockseer.splits import walk_forward_splits


@pytest.fixture
def prices() -> pd.DataFrame:
    """A synthetic random walk -- deterministic, and genuinely unpredictable."""
    rng = np.random.default_rng(0)
    n = 900
    idx = pd.bdate_range("2018-01-01", periods=n)
    ret = rng.normal(0.0004, 0.012, n)
    close = 100.0 * np.exp(np.cumsum(ret))
    high = close * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.004, n)))
    open_ = close * (1 + rng.normal(0, 0.003, n))
    volume = rng.lognormal(13, 0.4, n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


# --------------------------------------------------------------------------- #
# 1. No lookahead
# --------------------------------------------------------------------------- #
def test_features_use_no_future_data(prices):
    """Features at row t must be identical whether or not rows > t exist.

    This is the property that a stray ``.shift(-1)``, ``center=True`` window, or
    full-sample normalisation would break -- and the single most common reason a
    published stock model does not reproduce live.
    """
    full = build_features(prices)
    for cut in (400, 600, 899):
        truncated = build_features(prices.iloc[:cut])
        a = full.iloc[cut - 1]
        b = truncated.iloc[-1]
        pd.testing.assert_series_equal(a, b, check_names=False, rtol=1e-9, atol=1e-12)


def test_no_feature_correlates_suspiciously_with_the_future(prices):
    """On a random walk, no feature may show real correlation with tomorrow.

    A leak shows up here as a |rho| far outside the sampling noise band.
    """
    feats = build_features(prices)
    fwd = forward_return(prices["Close"], 1)
    mask = feats.notna().all(axis=1) & fwd.notna()
    ic = feats[mask].corrwith(fwd[mask], method="spearman").abs()
    # 3.5 standard errors of a zero-correlation Spearman estimate.
    bound = 3.5 / np.sqrt(mask.sum())
    offenders = ic[ic > bound]
    assert offenders.empty, f"suspicious feature/future correlation:\n{offenders}"


# --------------------------------------------------------------------------- #
# 2. Label alignment
# --------------------------------------------------------------------------- #
def test_forward_return_looks_forward(prices):
    close = prices["Close"]
    fwd = forward_return(close, 3)
    expected = close.iloc[103] / close.iloc[100] - 1.0
    assert fwd.iloc[100] == pytest.approx(expected)
    assert fwd.iloc[-3:].isna().all(), "last `horizon` rows must have no label"


def test_classification_label_matches_sign(prices):
    y, fwd = make_label(prices["Close"], horizon=5, task="classification")
    both = y.notna() & fwd.notna()
    assert ((y[both] == 1.0) == (fwd[both] > 0)).all()


def test_deadband_drops_only_small_moves(prices):
    y, fwd = make_label(prices["Close"], horizon=1, task="classification", deadband=0.005)
    dropped = y.isna() & fwd.notna()
    assert (fwd[dropped].abs() < 0.005).all()
    assert dropped.sum() > 0


def test_align_leaves_no_nans(prices):
    feats = build_features(prices)
    y, fwd = make_label(prices["Close"], 1)
    X, y2, fwd2 = align(feats, y, fwd)
    assert not X.isna().any().any()
    assert not y2.isna().any() and not fwd2.isna().any()
    assert X.index.equals(y2.index) and X.index.equals(fwd2.index)


# --------------------------------------------------------------------------- #
# 3. Split hygiene
# --------------------------------------------------------------------------- #
def test_splits_are_chronological_and_disjoint():
    folds = walk_forward_splits(2000, n_splits=5, min_train=750, embargo=1)
    assert len(folds) == 5
    seen = set()
    for f in folds:
        assert f.train.max() < f.test.min(), "training data must precede the test block"
        assert not seen & set(f.test.tolist()), "test blocks must not overlap"
        seen |= set(f.test.tolist())
    assert max(seen) == 1999, "the final fold must run to the end of the data"


def test_embargo_purges_overlapping_labels():
    """With a 5-day horizon, the last 5 training rows leak into the test block."""
    horizon = 5
    folds = walk_forward_splits(2000, n_splits=4, min_train=800, embargo=horizon)
    for f in folds:
        gap = f.test.min() - f.train.max() - 1
        assert gap >= horizon - 1, f"gap {gap} < embargo {horizon}"


def test_rolling_window_stays_bounded():
    folds = walk_forward_splits(3000, n_splits=5, min_train=600, expanding=False)
    assert all(len(f.train) <= 600 for f in folds)
    expanding = walk_forward_splits(3000, n_splits=5, min_train=600, expanding=True)
    assert expanding[-1].train.size > expanding[0].train.size


def test_too_little_data_raises():
    with pytest.raises(ValueError, match="Not enough rows"):
        walk_forward_splits(300, n_splits=5, min_train=750)


# --------------------------------------------------------------------------- #
# 4. Simulation arithmetic
# --------------------------------------------------------------------------- #
def test_always_long_reproduces_buy_and_hold(prices):
    """A permanently long, zero-cost position must equal buy-and-hold exactly."""
    preds = pd.DataFrame(
        {"score": 1.0, "y": 1.0, "fwd_ret": 0.0}, index=prices.index[300:]
    )
    pos = build_positions(preds, "classification", threshold=0.5)
    sim = simulate(preds, prices["Close"], pos, cost_bps=0.0)
    pd.testing.assert_series_equal(
        sim["strategy_equity"], sim["market_equity"], check_names=False
    )


def test_position_earns_the_next_days_return(prices):
    """pos[t] is set at the close of t and must earn the return of t -> t+1."""
    preds = pd.DataFrame({"score": 1.0, "y": 1.0, "fwd_ret": 0.0}, index=prices.index)
    pos = build_positions(preds, "classification")
    sim = simulate(preds, prices["Close"], pos, cost_bps=0.0)
    close = prices["Close"]
    expected = close.iloc[501] / close.iloc[500] - 1.0
    assert sim["gross_ret"].iloc[500] == pytest.approx(expected)


def test_costs_are_charged_on_position_change(prices):
    score = pd.Series(
        np.where(np.arange(len(prices)) % 2 == 0, 0.9, 0.1), index=prices.index
    )
    preds = pd.DataFrame({"score": score, "y": 1.0, "fwd_ret": 0.0})
    pos = build_positions(preds, "classification")
    free = simulate(preds, prices["Close"], pos, cost_bps=0.0)
    paid = simulate(preds, prices["Close"], pos, cost_bps=10.0)
    assert paid["strategy_ret"].sum() < free["strategy_ret"].sum()
    # Flipping every day means roughly one unit of turnover per day.
    assert paid["turnover"].mean() == pytest.approx(1.0, abs=0.05)


def test_smoothing_reduces_turnover(prices):
    rng = np.random.default_rng(1)
    preds = pd.DataFrame(
        {"score": rng.random(len(prices)), "y": 1.0, "fwd_ret": 0.0}, index=prices.index
    )
    raw = build_positions(preds, "classification", smooth=1)
    smooth = build_positions(preds, "classification", smooth=5)
    assert smooth.diff().abs().sum() < raw.diff().abs().sum()


def test_performance_stats_on_a_known_series():
    rets = pd.Series([0.10, -0.05, 0.02], index=pd.bdate_range("2020-01-01", periods=3))
    stats = performance_stats(rets)
    assert stats["total_return"] == pytest.approx(1.10 * 0.95 * 1.02 - 1.0)
    assert stats["hit_rate"] == pytest.approx(2 / 3)
    assert stats["max_drawdown"] == pytest.approx(-0.05)
