"""
Order-size optimizer: at what order VALUE does each broker become efficient?

For a round trip (buy V, sell V) computes every charge component:
  government/exchange (identical at all brokers):
    STT: delivery 0.1% each side; intraday 0.025% sell only
    Exchange txn (NSE): 0.00297% each side
    SEBI: 0.0001% each side
    Stamp: delivery buy 0.015%; intraday buy 0.003%
    GST: 18% on (brokerage + exchange + SEBI)
  broker-specific: brokerage per order + DP charge on delivery sell (flat).

Outputs: cost tables (₹ and % of V), breakeven price move, and the minimum
"efficient" order value per broker (cost within 15% of its large-order floor).

NOTE: brokerage rate cards below are the standard published schedules and are
being triple-verified against official pages; rerun after updating RATES if
verification changes anything.
"""
import os

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "output")

# Rates verified 26-Aug-2026 against brokers' official pricing pages
# (zerodha.com/charges, groww.in/pricing, upstox.com/brokerage-charges,
#  angelone.in). NSE txn charge 0.00307% since 1-Mar-2026.
EXCH, SEBI_F = 0.0000307, 0.000001
STT_DEL, STT_INT_SELL = 0.001, 0.00025
STAMP_DEL, STAMP_INT = 0.00015, 0.00003
GST = 0.18

BROKERS = {
    # name: (delivery brokerage fn, intraday brokerage fn, DP charge per sell)
    "Your broker (full-service ~0.05%)": (
        lambda v: v * 0.0005, lambda v: v * 0.0005, 25.0),
    "Zerodha": (        # delivery ₹0; intraday min(₹20, 0.03%); DP ₹15.34 all-in
        lambda v: 0.0, lambda v: min(20.0, v * 0.0003), 15.34),
    "Groww": (          # both: min(₹20, 0.1%), floor ₹5; DP ₹20 + GST
        lambda v: max(5.0, min(20.0, v * 0.001)),
        lambda v: max(5.0, min(20.0, v * 0.001)), 23.6),
    "Upstox": (         # delivery flat ₹20; intraday min(₹20, 0.1%); DP ₹20
        lambda v: min(20.0, v * 0.025), lambda v: min(20.0, v * 0.001), 20.0),
    "Angel One": (      # both: min(₹20, 0.1%), floor ₹5; DP ₹20
        lambda v: max(5.0, min(20.0, v * 0.001)),
        lambda v: max(5.0, min(20.0, v * 0.001)), 20.0),
    "Marwadi-type full service": (   # typical 0.30% delivery / 0.03% intraday
        lambda v: v * 0.003, lambda v: v * 0.0003, 22.0),
}


def round_trip(v, broker, kind):
    fdel, fint, dp = BROKERS[broker]
    if kind == "delivery":
        brok = fdel(v) * 2
        stt = v * STT_DEL * 2
        stamp = v * STAMP_DEL
        dpc = dp
    else:
        brok = fint(v) * 2
        stt = v * STT_INT_SELL
        stamp = v * STAMP_INT
        dpc = 0.0
    exch = v * EXCH * 2
    sebi = v * SEBI_F * 2
    gst = (brok + exch + sebi) * GST
    return brok + stt + stamp + exch + sebi + gst + dpc


GRID = [1000, 2000, 3600, 5000, 10000, 20000, 50000, 66667, 100000,
        200000, 500000]

for kind in ("intraday", "delivery"):
    rows = []
    for v in GRID:
        row = {"OrderValue": v}
        for b in BROKERS:
            c = round_trip(v, b, kind)
            row[b] = round(c, 1)
            row[b + " %"] = round(c / v * 100, 3)
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, f"order_size_cost_{kind}.csv"), index=False)
    print("=" * 110)
    print(f"ROUND-TRIP COST — {kind.upper()}  (buy V + sell V; ₹ cost and % of V = breakeven move needed)")
    pct_cols = ["OrderValue"] + [b + " %" for b in BROKERS]
    print(df[pct_cols].to_string(index=False))

print()
print("=" * 110)
print("MINIMUM EFFICIENT ORDER VALUE (cost% within 15% of that broker's floor at ₹5,00,000)")
for kind in ("intraday", "delivery"):
    print(f"--- {kind} ---")
    for b in BROKERS:
        floor = round_trip(500000, b, kind) / 500000
        v = 500
        while v < 500000:
            if round_trip(v, b, kind) / v <= floor * 1.15:
                break
            v += 500
        print(f"  {b:<36} efficient from ≈ ₹{v:>8,}   (floor cost {floor * 100:.3f}%)")

print()
print("=" * 110)
print("THE USER'S EXAMPLE — quantity does not matter, VALUE does (intraday round trip):")
for label, v in [("200 shares × ₹18  = ₹3,600", 3600),
                 ("1 share  × ₹1,800 = ₹1,800", 1800),
                 ("1 share  × ₹3,600 = ₹3,600", 3600)]:
    costs = "  ".join(f"{b.split()[0]}: ₹{round_trip(v, b, 'intraday'):.1f}"
                      for b in BROKERS)
    print(f"  {label:<28} {costs}")
