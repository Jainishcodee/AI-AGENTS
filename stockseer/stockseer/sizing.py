"""Position sizing, expectancy, and survival analysis.

Prediction accuracy gets all the attention; sizing decides the outcome. Two
traders with the identical signal, one risking 1% and one risking 20%, do not
have similar results with different variance -- one compounds and one is
eliminated. This module makes that difference computable instead of rhetorical.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .costs import CostModel


# --------------------------------------------------------------------------- #
# Sizing a single trade
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Position:
    qty: int
    entry: float
    stop: float
    target: float
    position_value: float
    risk_amount: float          # rupees at risk if the stop fills
    reward_amount: float        # rupees gained if the target fills
    costs: float                # round-trip charges
    net_risk: float             # loss including costs
    net_reward: float           # gain after costs
    rr_gross: float
    rr_net: float
    pct_of_capital: float

    def describe(self) -> str:
        return (
            f"  qty {self.qty} @ {self.entry:.2f}  "
            f"(Rs {self.position_value:,.0f}, {self.pct_of_capital * 100:.0f}% of capital)\n"
            f"  stop {self.stop:.2f} -> lose Rs {self.net_risk:,.0f}   "
            f"target {self.target:.2f} -> make Rs {self.net_reward:,.0f}\n"
            f"  costs Rs {self.costs:,.0f}   "
            f"R:R {self.rr_gross:.2f} gross / {self.rr_net:.2f} net of costs"
        )


def size_position(
    capital: float,
    entry: float,
    stop: float,
    target: float,
    risk_pct: float = 0.01,
    max_position_pct: float = 1.0,
    leverage: float = 1.0,
    delivery: bool = False,
    model: CostModel | None = None,
) -> Position:
    """Risk-first sizing: choose quantity so a stop-out costs exactly `risk_pct`.

    Note the direction of the logic. You do not pick a quantity and discover your
    risk; you pick your risk and derive the quantity. The stop distance therefore
    sets the size -- a tight stop buys a big position, a wide stop a small one,
    and the rupees at risk stay constant either way.
    """
    model = model or CostModel()
    if stop >= entry:
        raise ValueError("stop must sit below entry for a long position")
    if target <= entry:
        raise ValueError("target must sit above entry for a long position")

    risk_amount = capital * risk_pct
    per_share_risk = entry - stop
    qty = int(risk_amount // per_share_risk)

    # Cap by buying power before anything else.
    max_value = capital * max_position_pct * leverage
    qty = min(qty, int(max_value // entry))
    qty = max(qty, 0)

    position_value = qty * entry
    costs = model.round_trip(entry, target, qty, delivery)["total"] if qty else 0.0
    gross_risk = qty * per_share_risk
    gross_reward = qty * (target - entry)

    return Position(
        qty=qty,
        entry=entry,
        stop=stop,
        target=target,
        position_value=position_value,
        risk_amount=gross_risk,
        reward_amount=gross_reward,
        costs=costs,
        net_risk=gross_risk + costs,
        net_reward=gross_reward - costs,
        rr_gross=gross_reward / gross_risk if gross_risk else float("nan"),
        rr_net=(gross_reward - costs) / (gross_risk + costs) if gross_risk else float("nan"),
        pct_of_capital=position_value / capital if capital else 0.0,
    )


def atr_stop(entry: float, atr: float, multiple: float = 1.5) -> float:
    """Volatility-scaled stop. A fixed 2% stop is arbitrary; 1.5 ATR is not.

    Placing the stop inside the stock's normal daily noise guarantees you are
    taken out by randomness before your thesis has a chance to be right or wrong.
    """
    return entry - multiple * atr


# --------------------------------------------------------------------------- #
# Expectancy
# --------------------------------------------------------------------------- #
def expectancy(win_rate: float, rr_net: float) -> float:
    """Expected profit per trade, in units of risk (R).

    Positive is the entire game. A 40% win rate at 3R net is a strong system;
    a 70% win rate at 0.3R net loses money. Win rate alone tells you nothing.
    """
    return win_rate * rr_net - (1.0 - win_rate)


def required_win_rate(rr_net: float) -> float:
    """Break-even win rate for a given net reward:risk."""
    return 1.0 / (1.0 + rr_net)


def kelly_fraction(win_rate: float, rr_net: float) -> float:
    """Kelly-optimal risk fraction. Treat it as a ceiling you never approach.

    Full Kelly maximises long-run growth but produces drawdowns most people
    cannot sit through; practitioners use a quarter to a half of it.
    """
    if rr_net <= 0:
        return 0.0
    return max(0.0, (win_rate * (1.0 + rr_net) - 1.0) / rr_net)


# --------------------------------------------------------------------------- #
# Survival: does the plan reach the target before it reaches zero?
# --------------------------------------------------------------------------- #
@dataclass
class SurvivalResult:
    p_hit_target: float
    p_ruin: float
    p_neither: float
    median_final: float
    p5_final: float
    p95_final: float
    median_trades_to_target: float
    median_max_drawdown: float
    expectancy_r: float
    breakeven_win_rate: float
    kelly: float
    cost_per_r: float
    cost_per_trade_rs: float
    requested_risk_pct: float
    effective_risk_pct: float   # what buying power actually allows
    total_costs_median: float
    p_edge_negative: float      # share of paths whose true win rate is below break-even
    win_rate_p5: float
    win_rate_p95: float


def simulate_survival(
    capital: float,
    target_profit: float,
    win_rate: float,
    rr_gross: float,
    risk_pct: float,
    stop_pct: float,
    max_trades: int = 500,
    ruin_level: float = 0.5,
    delivery: bool = False,
    leverage: float = 1.0,
    model: CostModel | None = None,
    n_paths: int = 20_000,
    seed: int = 7,
    win_rate_confidence: int = 30,
    gap_prob: float = 0.03,
    gap_multiple: float = 2.5,
) -> SurvivalResult:
    """Monte Carlo the whole plan, costs and uncertainty included.

    Each trade risks ``risk_pct`` of *current* capital across a ``stop_pct``
    stop, which fixes the position size and therefore the rupee costs. A path
    ends when it reaches the profit target, falls to ``ruin_level`` of starting
    capital, or runs out of trades.

    Two things separate this from the usual expectancy-times-trades arithmetic,
    and both dominate the answer:

    **You do not know your win rate.** ``win_rate`` is an *estimate*, and
    ``win_rate_confidence`` says how many trades it rests on. Each path draws its
    own true win rate from Beta(w*n, (1-w)*n). Claiming 55% after 30 trades means
    the truth is plausibly anywhere from 37% to 73%, and a meaningful share of
    those paths sit below break-even. Assuming the estimate is exact is what makes
    naive simulations report a 100% success rate -- it assumes away the only thing
    that actually matters.

    **Stops do not always hold.** With probability ``gap_prob`` a stop gaps and
    the loss is ``gap_multiple`` times intended -- an overnight gap, a circuit, a
    news print. Rare, and responsible for a large share of real blow-ups.
    """
    model = model or CostModel()
    rng = np.random.default_rng(seed)

    # Per-path true win rate, drawn from the uncertainty around the estimate.
    n_conf = max(2, int(win_rate_confidence))
    a = max(1e-6, win_rate * n_conf)
    b = max(1e-6, (1.0 - win_rate) * n_conf)
    true_wr = rng.beta(a, b, size=n_paths)

    equity = np.full(n_paths, capital, dtype="float64")
    peak = equity.copy()
    max_dd = np.zeros(n_paths)
    costs_paid = np.zeros(n_paths)
    trades_taken = np.zeros(n_paths)
    hit = np.zeros(n_paths, dtype=bool)
    ruined = np.zeros(n_paths, dtype=bool)

    goal = capital + target_profit
    floor = capital * ruin_level

    for _ in range(max_trades):
        live = ~(hit | ruined)
        if not live.any():
            break

        risk_amt = equity * risk_pct
        # Position size follows from the stop distance, then gets capped by
        # available buying power.
        pos_value = np.minimum(risk_amt / stop_pct, equity * leverage)
        # Re-derive the true risk after the cap, so a capped position does not
        # silently over-report how much is on the line.
        risk_amt = pos_value * stop_pct

        cost = model.round_trip_vectorized(pos_value, delivery)

        won = rng.random(n_paths) < true_wr
        # A losing trade normally costs 1R; occasionally the stop gaps and it
        # costs several. This tail is small in frequency and large in effect.
        gapped = rng.random(n_paths) < gap_prob
        loss_mult = np.where(gapped, gap_multiple, 1.0)
        pnl = np.where(won, risk_amt * rr_gross, -risk_amt * loss_mult) - cost

        equity = np.where(live, equity + pnl, equity)
        costs_paid = np.where(live, costs_paid + cost, costs_paid)
        trades_taken = np.where(live, trades_taken + 1, trades_taken)

        peak = np.maximum(peak, equity)
        max_dd = np.maximum(max_dd, 1.0 - equity / peak)

        hit |= live & (equity >= goal)
        ruined |= live & (equity <= floor)

    reached = trades_taken[hit]

    # Express costs in units of risk (R) at the opening position size, so
    # expectancy and break-even win rate are reported net rather than gross.
    # This is where a small account gets hurt: the flat components of the
    # schedule do not shrink with the position, so cost-per-R rises as capital
    # falls -- the account gets harder to trade exactly as it gets smaller.
    # Risking `risk_pct` across a `stop_pct` stop needs a position of
    # risk_pct/stop_pct times capital. Beyond `leverage` you simply cannot fund
    # it, so the achievable risk is capped -- surfaced rather than swallowed.
    effective_risk_pct = min(risk_pct, stop_pct * leverage)
    pos0 = min(capital * risk_pct / stop_pct, capital * leverage)
    risk0 = pos0 * stop_pct
    cost0 = float(model.round_trip_vectorized(np.array([pos0]), delivery)[0])
    cost_r = cost0 / risk0 if risk0 > 0 else float("inf")

    rr_net = rr_gross - cost_r
    breakeven_wr = (1.0 + cost_r) / (1.0 + rr_gross)
    return SurvivalResult(
        p_hit_target=float(hit.mean()),
        p_ruin=float(ruined.mean()),
        p_neither=float((~hit & ~ruined).mean()),
        median_final=float(np.median(equity)),
        p5_final=float(np.percentile(equity, 5)),
        p95_final=float(np.percentile(equity, 95)),
        median_trades_to_target=float(np.median(reached)) if reached.size else float("nan"),
        median_max_drawdown=float(np.median(max_dd)),
        expectancy_r=expectancy(win_rate, rr_net),
        # A win must clear rr_gross - cost_r, and a loss now costs 1 + cost_r,
        # so break-even sits at (1 + cost_r) / (1 + rr_gross).
        breakeven_win_rate=breakeven_wr,
        kelly=kelly_fraction(win_rate, rr_net),
        cost_per_r=cost_r,
        cost_per_trade_rs=cost0,
        requested_risk_pct=risk_pct,
        effective_risk_pct=effective_risk_pct,
        total_costs_median=float(np.median(costs_paid)),
        p_edge_negative=float((true_wr < breakeven_wr).mean()),
        win_rate_p5=float(np.percentile(true_wr, 5)),
        win_rate_p95=float(np.percentile(true_wr, 95)),
    )
