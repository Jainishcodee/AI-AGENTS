"""Cost model and sizing tests.

The cost figures are checked against a hand-computed NSE contract note, because
a cost model that is quietly wrong makes every downstream number wrong in the
flattering direction.
"""

from __future__ import annotations

import numpy as np
import pytest

from stockseer.costs import CostModel, breakeven_move
from stockseer.sizing import (
    expectancy,
    kelly_fraction,
    required_win_rate,
    simulate_survival,
    size_position,
)


@pytest.fixture
def model() -> CostModel:
    return CostModel()


# --------------------------------------------------------------------------- #
# Costs
# --------------------------------------------------------------------------- #
def test_intraday_round_trip_matches_hand_computation(model):
    """Rs 40,000 intraday round trip on a discount broker.

        brokerage  min(0.03% x 40000, 20) = 12 per leg  x2 =  24.00
        STT        0.025% x 40000 (sell only)           =  10.00
        exchange   0.00297% x 40000 x 2                 =   2.376
        SEBI+IPFT  0.0001% x 80000                      =   0.16
        stamp      0.003% x 40000 (buy only)            =   1.20
        GST        18% x (24 + 2.376 + 0.16)            =   4.777
                                                          -------
                                                           42.51
    """
    rt = model.round_trip(400.0, 400.0, 100)
    assert rt["total"] == pytest.approx(42.51, abs=0.05)
    assert rt["as_pct_of_position"] == pytest.approx(0.00106, abs=0.00005)


def test_brokerage_cap_binds_on_large_positions(model):
    """Above ~Rs 66,700 the percentage brokerage exceeds the Rs 20 cap."""
    small = model.leg(40_000, "buy")["brokerage"]
    large = model.leg(500_000, "buy")["brokerage"]
    assert small == pytest.approx(12.0)
    assert large == pytest.approx(20.0), "cap must bind"


def test_delivery_costs_more_than_intraday(model):
    """0.1% STT on both legs plus DP charges dwarf the intraday schedule."""
    intraday = model.round_trip(400.0, 400.0, 100, delivery=False)["total"]
    delivery = model.round_trip(400.0, 400.0, 100, delivery=True)["total"]
    assert delivery > intraday * 2


def test_vectorized_matches_scalar(model):
    """The Monte Carlo path and the single-trade path must agree."""
    for turnover in (5_000.0, 40_000.0, 250_000.0):
        qty = int(turnover // 100.0)
        scalar = model.round_trip(100.0, 100.0, qty)["total"]
        vector = float(model.round_trip_vectorized(np.array([turnover]))[0])
        assert vector == pytest.approx(scalar, rel=1e-9)


def test_small_positions_are_proportionally_punished(model):
    """The flat components mean cost-per-rupee rises as the position shrinks.

    This is the effect that makes a small account structurally harder to trade,
    and it is exactly what a flat "5 bps" assumption hides.
    """
    tiny = breakeven_move(100.0, 50, model)      # Rs 5,000
    large = breakeven_move(100.0, 5_000, model)  # Rs 5,00,000
    assert tiny > large


# --------------------------------------------------------------------------- #
# Sizing
# --------------------------------------------------------------------------- #
def test_size_position_risks_the_requested_amount():
    pos = size_position(capital=100_000, entry=500.0, stop=490.0,
                        target=520.0, risk_pct=0.01)
    assert pos.qty == 100                      # Rs 1,000 risk / Rs 10 per share
    assert pos.risk_amount == pytest.approx(1_000.0)
    assert pos.reward_amount == pytest.approx(2_000.0)
    assert pos.rr_gross == pytest.approx(2.0)
    assert pos.rr_net < pos.rr_gross           # costs must erode it


def test_tighter_stop_buys_a_bigger_position():
    wide = size_position(100_000, 500.0, 480.0, 540.0, risk_pct=0.01)
    tight = size_position(100_000, 500.0, 495.0, 540.0, risk_pct=0.01)
    assert tight.qty > wide.qty
    assert tight.risk_amount == pytest.approx(wide.risk_amount, rel=0.05)


def test_buying_power_caps_the_position():
    """A very tight stop implies a position larger than the account can fund."""
    pos = size_position(50_000, 500.0, 499.5, 520.0, risk_pct=0.02, leverage=1.0)
    assert pos.position_value <= 50_000 + 1e-6
    assert pos.pct_of_capital <= 1.0


def test_invalid_levels_raise():
    with pytest.raises(ValueError, match="stop"):
        size_position(100_000, 500.0, 510.0, 520.0)
    with pytest.raises(ValueError, match="target"):
        size_position(100_000, 500.0, 490.0, 480.0)


# --------------------------------------------------------------------------- #
# Expectancy
# --------------------------------------------------------------------------- #
def test_expectancy_sign():
    assert expectancy(0.55, 1.5) > 0
    assert expectancy(0.35, 1.5) < 0
    # High win rate with poor payoff still loses -- the classic retail trap.
    assert expectancy(0.70, 0.3) < 0


def test_required_win_rate_is_the_zero_of_expectancy():
    for rr in (0.5, 1.0, 1.5, 3.0):
        assert expectancy(required_win_rate(rr), rr) == pytest.approx(0.0, abs=1e-12)


def test_kelly_is_zero_without_an_edge():
    assert kelly_fraction(required_win_rate(2.0), 2.0) == pytest.approx(0.0, abs=1e-12)
    assert kelly_fraction(0.30, 1.0) == 0.0
    assert kelly_fraction(0.60, 2.0) > 0


# --------------------------------------------------------------------------- #
# Survival
# --------------------------------------------------------------------------- #
def _sim(**kw):
    base = dict(
        capital=100_000, target_profit=50_000, win_rate=0.55, rr_gross=1.5,
        risk_pct=0.02, stop_pct=0.02, max_trades=300, n_paths=4_000,
    )
    return simulate_survival(**{**base, **kw})


def test_probabilities_sum_to_one():
    r = _sim()
    assert r.p_hit_target + r.p_ruin + r.p_neither == pytest.approx(1.0, abs=1e-9)


def test_uncertainty_creates_a_downside_tail():
    """A confidently-known edge looks safe; an estimated one does not.

    This is the whole point of the Beta draw. Without it the simulation reports
    a ~100% success rate, which is how naive plans get built.
    """
    confident = _sim(win_rate_confidence=100_000)
    unsure = _sim(win_rate_confidence=10)
    assert confident.p_ruin < unsure.p_ruin
    assert unsure.p_edge_negative > confident.p_edge_negative
    assert unsure.win_rate_p95 - unsure.win_rate_p5 > 0.2


def test_no_edge_means_no_amount_of_trading_helps():
    r = _sim(win_rate=0.35, win_rate_confidence=100_000)
    assert r.expectancy_r < 0
    assert r.p_ruin > 0.9


def test_oversizing_raises_ruin_without_raising_success():
    """Past Kelly, more risk buys you volatility, not growth.

    Needs leverage to be expressible at all: risking 25% across a 2% stop
    requires a position 12.5x capital, so at 1x the cap silently makes it
    identical to the sane plan.
    """
    sane = _sim(risk_pct=0.02, leverage=5.0, win_rate_confidence=30)
    reckless = _sim(risk_pct=0.25, leverage=5.0, win_rate_confidence=30)
    assert reckless.effective_risk_pct > sane.effective_risk_pct
    assert reckless.p_ruin > sane.p_ruin


def test_unfundable_risk_is_reported_not_swallowed():
    """Requesting more risk than buying power allows must be visible."""
    r = _sim(risk_pct=0.25, stop_pct=0.02, leverage=1.0)
    assert r.requested_risk_pct == pytest.approx(0.25)
    assert r.effective_risk_pct == pytest.approx(0.02), "capped at stop x leverage"


def test_costs_scale_the_breakeven_win_rate():
    cheap = _sim(capital=1_000_000)
    dear = _sim(capital=20_000)
    assert dear.cost_per_r > cheap.cost_per_r
    assert dear.breakeven_win_rate > cheap.breakeven_win_rate


def test_gaps_hurt():
    calm = _sim(gap_prob=0.0, win_rate_confidence=100_000)
    gappy = _sim(gap_prob=0.15, gap_multiple=3.0, win_rate_confidence=100_000)
    assert gappy.p_ruin > calm.p_ruin
