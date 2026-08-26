"""
Reconciled per-FY P&L.

Runs the base engine (portfolio_analysis.py), then corrects per-FY delivery
gross P&L using the broker's authoritative per-scrip lifetime numbers:

  gap(scrip) = broker delivery gross  -  engine delivery gross
  (the gap exists only where cost basis is missing in the tradebooks,
   i.e. IPO-allotment / pre-Apr-2024 shares that were later sold)

Each scrip's gap is allocated to financial years in proportion to the sell
value of that scrip's *unmatched* sells in each FY (those sells are exactly
where the missing basis was consumed). Scrips with no unmatched sells keep
their engine number.

Output: output/fy_summary_reconciled.csv + printed report.
"""
import os
import re
import runpy

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "output")

ns = runpy.run_path(os.path.join(BASE, "portfolio_analysis.py"))
realized = ns["realized"]
unmatched = ns["unmatched"]
delivery_scrips = ns["delivery_scrips"]
intraday_scrips = ns["intraday_scrips"]
fy_table = ns["fy_table"]
fy_of = ns["fy_of"]


def norm(s):
    s = re.sub(r"[^A-Z0-9]", "", str(s).upper())
    return s[:10]


# symbol -> normalized company-name keys (intraday table carries real names)
sym_names = {}
for _, r in intraday_scrips.iterrows():
    sym_names.setdefault(r["Scrip Symbol"], set()).add(norm(r["Company Name"]))
for _, r in delivery_scrips.iterrows():
    sym_names.setdefault(r["Scrip Symbol"], set()).add(norm(r["Company Name"]))
    sym_names[r["Scrip Symbol"]].add(norm(r["Scrip Symbol"]))

name_to_sym = {}
for sym, keys in sym_names.items():
    for k in keys:
        name_to_sym[k] = sym

MANUAL = {  # tradebook names whose 10-char prefix doesn't hit any broker key
    norm("BLUESTONE JEWEL LFSTL LTD"): "BLUESTONE",
    norm("BlueStone Jewellery"): "BLUESTONE",
    norm("BHARAT COKING COAL LTD"): "BHARATCOAL",
}
name_to_sym.update(MANUAL)


def to_sym(name):
    return name_to_sym.get(norm(name), norm(name))


# engine delivery gross per broker symbol
eng = realized[realized["Kind"] == "delivery"].copy()
eng["Sym"] = eng["Scrip"].map(to_sym)
eng_by_sym = eng.groupby("Sym")["GrossPnL"].sum()

brk_by_sym = delivery_scrips.groupby("Scrip Symbol")["Gross PnL"].sum()

gap = (brk_by_sym.reindex(brk_by_sym.index.union(eng_by_sym.index)).fillna(0.0)
       - eng_by_sym.reindex(brk_by_sym.index.union(eng_by_sym.index)).fillna(0.0))
gap = gap[gap.abs() > 1.0]

# unmatched sell value per (symbol, FY) drives the allocation weights
um = unmatched.copy()
um["Sym"] = um["Scrip"].map(to_sym)
um["FY"] = um["Date"].map(fy_of)
um.loc[um["FY"] == "FY2026-27", "FY"] = "FY2026-27*"
um_w = um.groupby(["Sym", "FY"])["SellValue"].sum()

# fallback FY per symbol: FY of that scrip's last engine delivery sell
last_fy = (eng.sort_values("Date").groupby("Sym")["Date"].last().map(fy_of)
           .str.replace("FY2026-27", "FY2026-27*", regex=False))

alloc = {fy: 0.0 for fy in ["FY2024-25", "FY2025-26", "FY2026-27*"]}
unallocated = 0.0
for sym, g in gap.items():
    if sym in um_w.index.get_level_values(0):
        w = um_w.loc[sym]
        for fy, v in (w / w.sum()).items():
            alloc[fy] += g * v
    elif sym in last_fy.index:
        alloc[last_fy[sym]] += g
    else:
        unallocated += g   # pre-FY25 scrip never traded in the 3 tradebooks

rec = fy_table.set_index("FY").copy()
rec["DeliveryGrossAdj"] = [round(rec.loc[fy, "DeliveryGross"] + alloc[fy], 2)
                           for fy in rec.index]
rec["GrossRealizedAdj"] = rec["IntradayGross"] + rec["DeliveryGrossAdj"]
rec["NetAfterAllChargesAdj"] = (rec["GrossRealizedAdj"] - rec["TotalCharges"]).round(2)
rec.to_csv(os.path.join(OUT, "fy_summary_reconciled.csv"))

print("=" * 90)
print("RECONCILED PER-FY P&L (delivery corrected to broker per-scrip lifetime numbers)")
print("=" * 90)
cols = ["IntradayGross", "DeliveryGrossAdj", "GrossRealizedAdj",
        "TradeCharges", "NonTradeCharges", "NetAfterAllChargesAdj"]
print(rec[cols].to_string())
print(f"\nGap allocated per FY: { {k: round(v, 2) for k, v in alloc.items()} }")
print(f"Unallocated (pre-FY25 scrips): {unallocated:,.2f}")

print("\n--- Ties back to broker lifetime? ---")
tot_gross = rec["GrossRealizedAdj"].sum()
tot_net_trade = tot_gross - rec["TradeCharges"].sum()
print(f"  Sum adj gross 3 FYs : {tot_gross:>12,.2f}  (broker lifetime 58,504.69; "
      f"residual = pre-FY25 trading)")
print(f"  Sum net of trade chg: {tot_net_trade:>12,.2f}  (broker lifetime net -25,490.52)")
print(f"  Sum net of ALL chg  : {rec['NetAfterAllChargesAdj'].sum():>12,.2f}")

print("\n--- FY2026-27 cross-check vs app screenshot ---")
print(f"  Adj gross realized  : {rec.loc['FY2026-27*', 'GrossRealizedAdj']:>12,.2f}  (app: 26,002.89)")
print(f"  Net of trade charges: {rec.loc['FY2026-27*', 'GrossRealizedAdj'] - rec.loc['FY2026-27*', 'TradeCharges']:>12,.2f}  (app: 1,558.56)")
