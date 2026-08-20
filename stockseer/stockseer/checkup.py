"""One command to answer: how risky is this, and how much should I buy?

Everything needed for that decision already existed, scattered across the
volatility code, the cost model and the position sizer. Scattered is the same
as missing when the decision takes thirty seconds -- so this pulls it into one
plain-language answer.

Deliberately says nothing about direction. It sizes the bet; it does not pick it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .costs import CostModel
from .data import load_prices_live
from .sizing import size_position


@dataclass
class Checkup:
    symbol: str
    price: float
    typical_move: float        # median absolute daily move
    ann_vol: float
    worst_day: float
    worst_day_on: str
    max_drawdown: float
    from_high: float
    atr_pct: float
    down_days_5pct: int        # days it fell more than 5%
    years: float
    # Sizing
    qty: int
    position_value: float
    stop: float
    target: float
    risk_rupees: float
    reward_rupees: float
    costs: float
    pct_of_capital: float
    turnover_cr: float
    above_200d: float
    rr_net: float
    verdict: str = ""
    good: list[str] = None      # type: ignore[assignment]
    bad: list[str] = None       # type: ignore[assignment]


def judge(k: "Checkup") -> tuple[str, list[str], list[str]]:
    """Verdict on whether this is a sane risk -- never on direction.

    Every rule here is about survivability: can you get out, can one trade hurt
    you, is the stop far enough from noise, does the reward justify the risk.
    Nothing in this function knows or claims anything about the price rising.
    """
    good: list[str] = []
    bad: list[str] = []

    # Liquidity first. An illiquid stock is a trap regardless of its chart:
    # the loss you planned is not the loss you take when nobody will buy.
    if k.turnover_cr >= 5:
        good.append(f"Easy to sell - about Rs.{k.turnover_cr:,.0f} crore trades daily")
    elif k.turnover_cr >= 1:
        good.append(f"Sellable - about Rs.{k.turnover_cr:,.1f} crore trades daily")
    else:
        bad.append(f"HARD TO SELL - only Rs.{k.turnover_cr:,.1f} crore trades daily. "
                   "In a fall, buyers disappear and you may be stuck")

    if k.qty == 0:
        bad.append(f"One share costs Rs.{k.price:,.0f} - too expensive to size "
                   "safely with your capital")
    elif k.qty < 5:
        bad.append(f"You could only buy {k.qty} shares. Too few to exit in parts")
    else:
        good.append(f"You can buy {k.qty} shares and still cap the loss at "
                    f"Rs.{k.risk_rupees:,.0f}")

    if k.ann_vol > 0.60:
        bad.append(f"VERY jumpy - swings {k.ann_vol * 100:.0f}% a year "
                   "(market is ~15%). Moves fast in both directions")
    elif k.ann_vol > 0.40:
        bad.append(f"Jumpy - swings {k.ann_vol * 100:.0f}% a year vs ~15% "
                   "for the market")
    else:
        good.append(f"Reasonably steady - {k.ann_vol * 100:.0f}% swing a year")

    if k.above_200d > 1.00:
        bad.append(f"Stretched - {k.above_200d * 100:.0f}% above its 6-month "
                   "average price. A lot of good news is already in the price")
    elif k.above_200d > 0.40:
        bad.append(f"Well above its 6-month average ({k.above_200d * 100:.0f}%). "
                   "Buying after a big run means a worse entry")
    elif k.above_200d > 0:
        good.append("Above its 6-month average, so the trend is up")

    if k.max_drawdown < -0.70:
        bad.append(f"Has fallen {abs(k.max_drawdown) * 100:.0f}% before. "
                   "It can happen again")
    if k.down_days_5pct >= 10:
        bad.append(f"Fell more than 5% on {k.down_days_5pct} days this year")

    if k.rr_net >= 1.8:
        good.append(f"Good reward for the risk - risk Rs.{k.risk_rupees:,.0f} "
                    f"to make Rs.{k.reward_rupees:,.0f}")
    elif k.rr_net < 1.2:
        bad.append("Poor reward for the risk after costs")

    serious = sum(1 for b in bad if b.startswith(("HARD", "VERY", "One share")))
    if serious or len(bad) >= 4:
        verdict = "BAD BET"
    elif len(bad) >= 2:
        verdict = "RISKY - only with a small amount"
    else:
        verdict = "OK TO BET"
    return verdict, good, bad


def check(symbol: str, capital: float = 40_000.0, risk_pct: float = 0.02,
          stop_atr: float = 2.0, reward_multiple: float = 2.0,
          max_position_pct: float = 0.35, start: str = "2015-01-01") -> Checkup:
    """Measure the stock's own behaviour, then size a position against it.

    The stop comes from the stock's actual daily range (ATR), not a round 5%.
    A stop placed inside a stock's normal noise is not a stop -- it is a
    guarantee of being taken out by randomness before the idea is tested.
    """
    px = load_prices_live(symbol, start=start, min_rows=60)
    c, h, l = px["Close"], px["High"], px["Low"]
    ret = c.pct_change().dropna()
    price = float(c.iloc[-1])

    prev = c.shift(1)
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])

    worst_idx = ret.idxmin()
    dd = c / c.cummax() - 1.0

    stop = price - stop_atr * atr
    if stop <= 0:
        stop = price * 0.9
    target = price + reward_multiple * (price - stop)

    pos = size_position(
        capital=capital, entry=price, stop=stop, target=target,
        risk_pct=risk_pct, max_position_pct=max_position_pct,
        model=CostModel(),
    )

    sma200 = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else price
    turnover = float((c * px["Volume"]).tail(60).median() / 1e7)

    k = Checkup(
        symbol=symbol, price=price,
        typical_move=float(ret.abs().tail(252).median()),
        ann_vol=float(ret.tail(252).std() * np.sqrt(252)),
        worst_day=float(ret.min()), worst_day_on=str(worst_idx.date()),
        max_drawdown=float(dd.min()), from_high=float(dd.iloc[-1]),
        atr_pct=atr / price,
        down_days_5pct=int((ret.tail(252) <= -0.05).sum()),
        years=len(c) / 252.0,
        qty=pos.qty, position_value=pos.position_value,
        stop=stop, target=target,
        risk_rupees=pos.net_risk, reward_rupees=pos.net_reward,
        costs=pos.costs, pct_of_capital=pos.pct_of_capital,
        turnover_cr=turnover,
        above_200d=price / sma200 - 1.0 if sma200 > 0 else 0.0,
        rr_net=pos.rr_net,
        good=[], bad=[],
    )
    k.verdict, k.good, k.bad = judge(k)
    return k


def print_checkup(k: Checkup, capital: float) -> None:
    money = lambda v: f"Rs.{v:,.0f}"                                   # noqa: E731
    bar = "=" * 66

    print(f"\n{bar}")
    print(f" {k.symbol}    {money(k.price)}")
    print(bar)

    print("\n HOW RISKY IS IT")
    print(f"   Normal day        moves about {k.typical_move * 100:.1f}%")
    print(f"   Bad day           {k.worst_day * 100:.0f}%  (happened on {k.worst_day_on})")
    print(f"   Fell over 5%      {k.down_days_5pct} times in the last year")
    print(f"   Biggest fall      {k.max_drawdown * 100:.0f}% from its high")
    if k.from_high > -0.02:
        print("   Right now         at its highest ever price")
    else:
        print(f"   Right now         {k.from_high * 100:.0f}% below its high")

    if k.ann_vol > 0.40:
        note = "much jumpier than the market"
    elif k.ann_vol > 0.25:
        note = "jumpier than the market"
    else:
        note = "calmer than most"
    print(f"   Overall           {note} ({k.ann_vol * 100:.0f}% vs ~15% for NIFTY)")

    print(f"\n IF YOU BUY WITH {money(capital)}")
    if k.qty == 0:
        print(f"   One share costs {money(k.price)} -- more than your limit allows.")
        print(f"{bar}\n")
        return

    print(f"   Buy               {k.qty} shares = {money(k.position_value)}"
          f"  ({k.pct_of_capital * 100:.0f}% of your money)")
    print(f"   Sell if it drops  {money(k.stop)}   ->  you lose {money(k.risk_rupees)}")
    print(f"   Take profit at    {money(k.target)}   ->  you make {money(k.reward_rupees)}")
    print(f"   Brokerage + tax   {money(k.costs)}")

    print("\n WHY THESE NUMBERS")
    print(f"   The sell price is {k.atr_pct * 200:.1f}% below today -- twice this")
    print("   stock's normal daily swing, so ordinary movement will not")
    print("   trigger it. Only a real move down does.")
    print(f"   The loss is capped near 2% of your money, so being wrong")
    print("   several times in a row still leaves you trading.")

    print(f"\n{bar}")
    print(f"  VERDICT:  {k.verdict}")
    print(bar)
    if k.good:
        print("\n  GOOD")
        for g in k.good:
            print(f"    +  {g}")
    if k.bad:
        print("\n  BAD")
        for b in k.bad:
            print(f"    -  {b}")

    print("\n  WHAT THIS VERDICT MEANS")
    print("    It answers: is this a safe-sized bet for your money?")
    print("    It does NOT answer: will the price go up?")
    print("    Nothing can answer that second one. I tested it many ways.")
    print(f"{bar}\n")
