"""Turn a capital + target into the trading plan it actually implies.

You do not get to choose your target and your risk independently. Pick a profit
goal and a capital base, and the arithmetic hands you a required win rate, a
required number of trades, and a probability of getting wiped out first. This
module computes those instead of leaving them implicit.
"""

from __future__ import annotations

from .costs import CostModel, breakeven_move
from .sizing import simulate_survival

# Realistic reference points for a competent discretionary retail trader.
# Anything above these is not a plan, it is a hope.
GOOD_WIN_RATE = 0.55
GOOD_RR = 1.5


def plan_report(
    capital: float,
    target_profit: float,
    win_rate: float = GOOD_WIN_RATE,
    rr: float = GOOD_RR,
    risk_pct: float = 0.02,
    stop_pct: float = 0.02,
    max_trades: int = 500,
    delivery: bool = False,
    leverage: float = 1.0,
    win_rate_confidence: int = 30,
    gap_prob: float = 0.03,
    model: CostModel | None = None,
) -> None:
    model = model or CostModel()
    seg = "delivery" if delivery else "intraday"
    bar = "=" * 74

    res = simulate_survival(
        capital=capital, target_profit=target_profit, win_rate=win_rate,
        rr_gross=rr, risk_pct=risk_pct, stop_pct=stop_pct, max_trades=max_trades,
        delivery=delivery, leverage=leverage, model=model,
        win_rate_confidence=win_rate_confidence, gap_prob=gap_prob,
    )

    pos_value = min(capital * risk_pct / stop_pct, capital * leverage)
    price = 500.0  # nominal, for the flat-fee illustration
    qty = max(1, int(pos_value // price))
    be = breakeven_move(price, qty, model, delivery)

    print(f"\n{bar}")
    print(f" PLAN  |  capital Rs {capital:,.0f}  ->  target Rs {target_profit:,.0f}"
          f"  ({target_profit / capital * 100:.0f}% return)  |  {seg}")
    print(bar)

    print("\n-- ASSUMPTIONS ------------------------------------------------------")
    print(f" win rate ESTIMATE    : {win_rate * 100:.0f}%"
          f"   (a genuinely good retail trader is ~55%)")
    print(f"   based on {win_rate_confidence} trades -> the truth is plausibly"
          f" {res.win_rate_p5 * 100:.0f}%-{res.win_rate_p95 * 100:.0f}%")
    print(f" reward:risk          : {rr:.2f}   (before costs)")
    print(f" stop-gap risk        : {gap_prob * 100:.0f}% of losses run past the stop")
    print(f" risk per trade       : {risk_pct * 100:.1f}% of capital"
          f"   = Rs {capital * risk_pct:,.0f}")
    print(f" stop distance        : {stop_pct * 100:.1f}%"
          f"   -> position Rs {pos_value:,.0f}")
    if res.effective_risk_pct < res.requested_risk_pct - 1e-9:
        print(f"   NOTE: {risk_pct * 100:.1f}% risk across a {stop_pct * 100:.1f}% stop needs"
              f" {risk_pct / stop_pct:.1f}x leverage.")
        print(f"   At {leverage:.1f}x your real risk per trade is"
              f" {res.effective_risk_pct * 100:.1f}%, not {risk_pct * 100:.1f}%.")

    print("\n-- COST DRAG --------------------------------------------------------")
    print(f" round-trip per trade : Rs {res.cost_per_trade_rs:,.0f}"
          f"   on a Rs {pos_value:,.0f} position")
    print(f" cost per trade in R  : {res.cost_per_r:.3f}R"
          f"   <- fraction of your risk budget burned on charges")
    print(f" break-even move      : {be * 100:.3f}%"
          f"   <- how far it must move just to be flat")
    print(f" break-even win rate  : {res.breakeven_win_rate * 100:.1f}%"
          f"   <- below this you lose money by arithmetic")

    print("\n-- EDGE -------------------------------------------------------------")
    print(f" expectancy per trade : {res.expectancy_r:+.4f}R net of costs"
          f"   (if the estimate is right)")
    print(f" chance you have NO   : {res.p_edge_negative * 100:.1f}%"
          f"   <- share of paths whose true win rate")
    print(f"   edge at all                 sits below the {res.breakeven_win_rate * 100:.1f}%"
          " break-even line")
    if res.expectancy_r <= 0:
        print("   NEGATIVE. No amount of sizing rescues this -- more trades means"
              "\n   more certain loss. The win rate or the R:R has to improve first.")
    print(f" full Kelly risk      : {res.kelly * 100:.1f}% of capital per trade")
    print(f"   practitioners use a quarter to a half of Kelly"
          f" -> {res.kelly * 25:.1f}-{res.kelly * 50:.1f}%")
    if risk_pct > res.kelly and res.kelly > 0:
        print(f"   YOUR {risk_pct * 100:.1f}% IS ABOVE FULL KELLY -- mathematically"
              " growth-destroying,\n   even with a real edge.")

    print(f"\n-- OUTCOME ({max_trades} trades, 20,000 simulated paths) ----------------")
    print(f" reach the target     : {res.p_hit_target * 100:5.1f}%")
    print(f" lose half the account: {res.p_ruin * 100:5.1f}%")
    print(f" neither              : {res.p_neither * 100:5.1f}%")
    if res.median_trades_to_target == res.median_trades_to_target:
        print(f" trades to target     : {res.median_trades_to_target:.0f} (median, when reached)")
    print(f" median final capital : Rs {res.median_final:,.0f}")
    print(f" 5th / 95th pct       : Rs {res.p5_final:,.0f} / Rs {res.p95_final:,.0f}")
    print(f" median max drawdown  : {res.median_max_drawdown * 100:.1f}%")
    print(f" median costs paid    : Rs {res.total_costs_median:,.0f}"
          f"   ({res.total_costs_median / capital * 100:.0f}% of starting capital)")

    print(f"\n{bar}")
    print(_verdict(res, capital, target_profit))
    print(f"{bar}\n")


def _verdict(res, capital: float, target: float) -> str:
    ratio = target / capital
    if res.expectancy_r <= 0:
        return (" VERDICT: negative expectancy. This plan loses money on average"
                " regardless of\n how many trades you take. Fix the edge, not the sizing.")
    if res.p_ruin > res.p_hit_target:
        return (f" VERDICT: you are more likely to lose half the account"
                f" ({res.p_ruin * 100:.0f}%) than to\n reach the target"
                f" ({res.p_hit_target * 100:.0f}%). The target is driving the risk,"
                " not the edge.")
    if ratio > 0.5:
        return (f" VERDICT: reachable in {res.p_hit_target * 100:.0f}% of paths, but a"
                f" {ratio * 100:.0f}% return demands\n risk that also produces a"
                f" {res.median_max_drawdown * 100:.0f}% median drawdown. Survivable, not comfortable.")
    return (f" VERDICT: {res.p_hit_target * 100:.0f}% of paths reach the target,"
            f" {res.p_ruin * 100:.0f}% halve the account.\n Expectancy is positive"
            " -- this is a plan you can actually run.")


def compare_capital(target_profit: float, levels: list[float], **kwargs) -> None:
    """The same target across capital levels. Shows why the base matters most."""
    print(f"\n Target Rs {target_profit:,.0f} at different capital levels")
    print(f" {'capital':>12}{'return needed':>15}{'P(target)':>12}"
          f"{'P(ruin)':>10}{'cost/R':>9}{'breakeven WR':>14}")
    print(" " + "-" * 72)
    for cap in levels:
        res = simulate_survival(capital=cap, target_profit=target_profit, **kwargs)
        print(f" {cap:>12,.0f}{target_profit / cap * 100:>14.0f}%"
              f"{res.p_hit_target * 100:>11.1f}%{res.p_ruin * 100:>9.1f}%"
              f"{res.cost_per_r:>9.3f}{res.breakeven_win_rate * 100:>13.1f}%")
    print()
