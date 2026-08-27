"""
What did the current broker effectively charge, and what would the same
activity have cost elsewhere?

Computes from the 3 tradebooks:
  - effective brokerage %% per side, split intraday vs delivery, per FY
  - distinct order counts (discount brokers charge per ORDER, not per trade)
  - simulated brokerage under per-order pricing models (rates passed as params
    so verified 2026 schedules can be plugged in)
"""
import os
import runpy

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
ns = runpy.run_path(os.path.join(BASE, "portfolio_analysis.py"))
trades = ns["trades"]
fy_summaries = ns["fy_summaries"]

trades = trades[trades["Value"] > 0].copy()
trades["Kind"] = trades["Order Type"].where(trades["Order Type"] == "Intraday",
                                            "Delivery")

print("=" * 88)
print("ACTUAL EFFECTIVE BROKERAGE OF CURRENT BROKER (from tradebooks)")
print("=" * 88)
g = (trades.groupby(["FY", "Kind"])
     .agg(Turnover=("Value", "sum"), Brokerage=("Brokerage", "sum"),
          TradeRows=("Value", "size"), Orders=("Order ID", "nunique")))
g["EffRatePct"] = (g["Brokerage"] / g["Turnover"] * 100).round(4)
g["AvgOrderValue"] = (g["Turnover"] / g["Orders"]).round(0)
print(g.to_string())

tot = (trades.groupby("Kind")
       .agg(Turnover=("Value", "sum"), Brokerage=("Brokerage", "sum"),
            Orders=("Order ID", "nunique")))
tot["EffRatePct"] = (tot["Brokerage"] / tot["Turnover"] * 100).round(4)
print("\nOverall:")
print(tot.to_string())

# ---- per-order values for simulation (order = distinct Order ID) ----
orders = (trades.groupby(["FY", "Kind", "Order ID"])["Value"].sum()
          .reset_index(name="OrderValue"))


def simulate(name, intraday_fn, delivery_fn):
    intr = orders[orders["Kind"] == "Intraday"]["OrderValue"]
    deli = orders[orders["Kind"] == "Delivery"]["OrderValue"]
    ci = intr.map(intraday_fn).sum()
    cd = deli.map(delivery_fn).sum()
    print(f"{name:<46} intraday ₹{ci:>10,.0f}  delivery ₹{cd:>9,.0f}  "
          f"total ₹{ci + cd:>10,.0f}")
    return ci + cd


actual = trades["Brokerage"].sum()
print(f"\n{'ACTUAL brokerage paid (3 FYs)':<46} "
      f"intraday ₹{trades.loc[trades['Kind'] == 'Intraday', 'Brokerage'].sum():>10,.0f}  "
      f"delivery ₹{trades.loc[trades['Kind'] == 'Delivery', 'Brokerage'].sum():>9,.0f}  "
      f"total ₹{actual:>10,.0f}")

print("\nSIMULATED under per-order discount pricing (plug verified 2026 rates):")
z = simulate("Zerodha-style: delivery ₹0, intraday min(₹20, 0.03%)",
             lambda v: min(20.0, v * 0.0003), lambda v: 0.0)
u = simulate("₹20-flat style: min(₹20, 2.5%) both segments",
             lambda v: min(20.0, v * 0.025), lambda v: min(20.0, v * 0.025))
g5 = simulate("Groww-2025 style: min(₹20, 0.1%) floor ₹5, both",
              lambda v: max(5.0, min(20.0, v * 0.001)),
              lambda v: max(5.0, min(20.0, v * 0.001)))
print(f"\nEstimated 3-FY brokerage saving vs Zerodha-style: ₹{actual - z:,.0f}")
print(f"Estimated saving vs ₹20-flat style:               ₹{actual - u:,.0f}")

# GST rides on brokerage+txn charges, so saved brokerage also saves ~18% GST
print(f"(plus ~18% GST on whatever brokerage is saved)")

dp = sum(float(s.get("DP Charges", 0) or 0) for s in fy_summaries.values())
print(f"\nDP charges paid (3 FYs): ₹{dp:,.0f}  "
      f"(charged per sell-from-demat day; ₹15-25 range at most brokers)")
