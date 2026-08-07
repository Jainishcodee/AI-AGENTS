"""Indian equity transaction costs, modelled properly.

At institutional size, brokerage and taxes are a rounding error. At a retail
account under a few lakh they are one of the largest terms in the P&L, because
several of them are *flat* fees that do not shrink with your position. A model
that assumes "5 bps" hides exactly the effect that decides whether a small
account survives.

Defaults reflect discount brokers (Upstox / Dhan / Fyers / Angel One) and the
NSE/SEBI schedule current as of early 2026. **Verify against your own broker's
contract note** -- these change, and the whole point of this module is that the
numbers are real. Every rate is a constructor argument.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CostModel:
    """Charges for one leg or one round trip of an NSE equity trade.

    All percentage fields are fractions of turnover (0.0003 = 0.03%), not
    percentages, so nothing needs dividing by 100 downstream.
    """

    # Brokerage: discount brokers charge min(pct * turnover, cap) per order.
    brokerage_pct: float = 0.0003          # 0.03% intraday
    brokerage_cap: float = 20.0            # rupees per executed order
    delivery_brokerage_pct: float = 0.0    # most discount brokers: zero
    delivery_brokerage_cap: float = 0.0

    # Securities Transaction Tax
    stt_intraday_sell: float = 0.00025     # 0.025%, sell side only
    stt_delivery: float = 0.001            # 0.1%, both sides

    # Exchange, regulator, and stamp
    exchange_txn: float = 0.0000297        # NSE, both sides
    sebi_fee: float = 0.000001             # Rs 10 per crore
    ipft: float = 0.000001                 # NSE investor protection fund
    stamp_intraday_buy: float = 0.00003    # 0.003%, buy side only
    stamp_delivery_buy: float = 0.00015    # 0.015%, buy side only

    gst: float = 0.18                      # on brokerage + exchange + sebi

    # Depository charge on delivery sells -- flat per scrip, per day.
    dp_charge: float = 15.5                # CDSL + typical broker markup

    def _brokerage(self, turnover: float, delivery: bool) -> float:
        pct = self.delivery_brokerage_pct if delivery else self.brokerage_pct
        cap = self.delivery_brokerage_cap if delivery else self.brokerage_cap
        if pct <= 0.0:
            return 0.0
        return min(pct * turnover, cap) if cap > 0 else pct * turnover

    def leg(self, turnover: float, side: str, delivery: bool = False) -> dict[str, float]:
        """Charges for a single buy or sell leg."""
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")

        brokerage = self._brokerage(turnover, delivery)
        if delivery:
            stt = self.stt_delivery * turnover
        else:
            stt = self.stt_intraday_sell * turnover if side == "sell" else 0.0

        exch = self.exchange_txn * turnover
        sebi = self.sebi_fee * turnover
        ipft = self.ipft * turnover
        stamp = 0.0
        if side == "buy":
            stamp = (self.stamp_delivery_buy if delivery else self.stamp_intraday_buy) * turnover
        gst = self.gst * (brokerage + exch + sebi + ipft)
        dp = self.dp_charge if (delivery and side == "sell") else 0.0

        total = brokerage + stt + exch + sebi + ipft + stamp + gst + dp
        return {
            "brokerage": brokerage, "stt": stt, "exchange": exch, "sebi": sebi,
            "ipft": ipft, "stamp": stamp, "gst": gst, "dp": dp, "total": total,
        }

    def round_trip(
        self, entry_price: float, exit_price: float, qty: int, delivery: bool = False
    ) -> dict[str, float]:
        """Total cost of getting in and back out of a position."""
        buy = self.leg(entry_price * qty, "buy", delivery)
        sell = self.leg(exit_price * qty, "sell", delivery)
        total = buy["total"] + sell["total"]
        turnover = entry_price * qty
        return {
            "buy": buy["total"],
            "sell": sell["total"],
            "total": total,
            "as_pct_of_position": total / turnover if turnover else 0.0,
            "breakeven_move_pct": total / turnover if turnover else 0.0,
        }


    def round_trip_vectorized(self, turnover, delivery: bool = False):
        """Round-trip cost for an array of position values, in rupees.

        Same schedule as :meth:`round_trip`, expressed elementwise so a 20k-path
        Monte Carlo does not need a Python loop. Assumes the exit turnover
        approximates the entry turnover, which is accurate to within the size of
        the move itself -- immaterial for a cost estimate.
        """
        t = np.asarray(turnover, dtype="float64")
        pct = self.delivery_brokerage_pct if delivery else self.brokerage_pct
        cap = self.delivery_brokerage_cap if delivery else self.brokerage_cap

        if pct <= 0.0:
            per_leg = np.zeros_like(t)
        elif cap > 0:
            per_leg = np.minimum(pct * t, cap)
        else:
            per_leg = pct * t
        brokerage = 2.0 * per_leg

        stt = (self.stt_delivery * 2.0 if delivery else self.stt_intraday_sell) * t
        exch = self.exchange_txn * t * 2.0
        sebi = self.sebi_fee * t * 2.0
        ipft = self.ipft * t * 2.0
        stamp = (self.stamp_delivery_buy if delivery else self.stamp_intraday_buy) * t
        gst = self.gst * (brokerage + exch + sebi + ipft)
        dp = self.dp_charge if delivery else 0.0

        return brokerage + stt + exch + sebi + ipft + stamp + gst + dp


def breakeven_move(
    price: float, qty: int, model: CostModel | None = None, delivery: bool = False
) -> float:
    """How far the stock must move, in percent, just to get back to flat.

    This is the number small accounts underestimate most. Every trade starts
    this far underwater.
    """
    model = model or CostModel()
    rt = model.round_trip(price, price, qty, delivery)
    return rt["as_pct_of_position"]
