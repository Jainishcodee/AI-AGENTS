"""
Portfolio analysis engine.

Parses the 4 broker Excel files in this folder:
  - 0cfdbedc...xlsx : Overall Equity P&L (16-Jun-2022 -> 25-Aug-2026), per-scrip
                      delivery & intraday tables (broker-computed, authoritative)
  - f3bdcf4d...xlsx : TradeBook + charges FY2024-25
  - c991636e...xlsx : TradeBook + charges FY2025-26
  - 454ddc26...xlsx : TradeBook + charges FY2026-27 (to 25-Aug-2026)

Computes:
  - per-FY realized P&L (intraday same-day pairing + delivery FIFO), net of charges
  - monthly gross P&L and charges time series
  - per-scrip lifetime winners/losers (from broker's own tables)
  - charges breakdown per FY by component
Writes tidy CSVs to ./output/ and prints a reconciliation report.
"""
import os
from collections import defaultdict, deque

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "output")
os.makedirs(OUT, exist_ok=True)

PNL_FILE = os.path.join(BASE, "0cfdbedc-0540-4a52-8afe-c3e315871a48.xlsx")
TRADEBOOKS = {
    "FY2024-25": os.path.join(BASE, "f3bdcf4d-b1db-4403-8352-b82a9f3e381e.xlsx"),
    "FY2025-26": os.path.join(BASE, "c991636e-4bd9-4e2e-93e8-736ec1769a92.xlsx"),
    "FY2026-27*": os.path.join(BASE, "454ddc26-53cd-40cf-adc8-da2010eb3d90.xlsx"),
}
CHARGE_COLS = ["Brokerage", "GST", "STT", "Sebi Tax", "Exchange Turnover Charges",
               "Stamp Duty", "Other Charges", "IPFT Charges"]


# ---------------------------------------------------------------- tradebooks
def parse_tradebook(path, fy):
    raw = pd.read_excel(path, sheet_name="TradesAndCharges", header=None)
    # summary block: label in col 0, value in col 1
    summary = {}
    for _, row in raw.iloc[:33].iterrows():
        if pd.notna(row[0]) and pd.notna(row[1]) and isinstance(row[0], str):
            summary[row[0].strip()] = row[1]
    # trade table: header row is the one whose col0 == 'Scrip/Contract'
    hdr_idx = raw.index[raw[0] == "Scrip/Contract"][0]
    cols = raw.iloc[hdr_idx].tolist()
    trades = raw.iloc[hdr_idx + 1:].copy()
    trades.columns = cols
    trades = trades[trades["Scrip/Contract"].notna()]
    trades = trades[trades["Buy/Sell"].isin(["Buy", "Sell"])]
    trades["Date"] = pd.to_datetime(trades["Date"])
    for c in ["Buy Price", "Sell Price", "Quantity"] + CHARGE_COLS:
        trades[c] = pd.to_numeric(trades[c], errors="coerce").fillna(0.0)
    trades["FY"] = fy
    trades["TradeCharges"] = trades[CHARGE_COLS].sum(axis=1)
    trades["Price"] = trades["Buy Price"].where(trades["Buy/Sell"] == "Buy",
                                               trades["Sell Price"])
    trades["Value"] = trades["Price"] * trades["Quantity"]
    return trades, summary


all_trades, fy_summaries = [], {}
for fy, path in TRADEBOOKS.items():
    t, s = parse_tradebook(path, fy)
    all_trades.append(t)
    fy_summaries[fy] = s
trades = pd.concat(all_trades, ignore_index=True).sort_values("Date").reset_index(drop=True)


# ------------------------------------------------- realized P&L computation
# Intraday: pair same scrip, same day, Order Type == Intraday.
# Unmatched intraday quantity spills into the delivery FIFO book.
# Delivery: FIFO per scrip across the full 3-FY timeline.
# Sells with no cost basis in the data (IPO allotments, pre-Apr-2024 buys)
# are excluded from P&L and reported separately.
realized_rows = []       # (date, scrip, kind, qty, pnl_gross)
unmatched_sells = []     # (date, scrip, qty, value)
fifo = defaultdict(deque)  # scrip -> deque of [qty, price]

day_groups = trades.groupby([trades["Date"].dt.normalize(), "Scrip/Contract"], sort=True)
for (day, scrip), g in day_groups:
    intr = g[g["Order Type"] == "Intraday"]
    deli = g[g["Order Type"] != "Intraday"]
    # --- intraday pairing
    bq, sq = intr.loc[intr["Buy/Sell"] == "Buy", "Quantity"].sum(), \
             intr.loc[intr["Buy/Sell"] == "Sell", "Quantity"].sum()
    bv = intr.loc[intr["Buy/Sell"] == "Buy", "Value"].sum()
    sv = intr.loc[intr["Buy/Sell"] == "Sell", "Value"].sum()
    if bq > 0 and sq > 0:
        m = min(bq, sq)
        pnl = m * (sv / sq - bv / bq)
        realized_rows.append((day, scrip, "intraday", m, pnl))
    if bq > sq and bq > 0:          # leftover long -> delivery book
        fifo[scrip].append([bq - sq, bv / bq])
    elif sq > bq and sq > 0:        # leftover short sell -> treat as delivery sell
        deli = pd.concat([deli, pd.DataFrame([{
            "Buy/Sell": "Sell", "Quantity": sq - bq, "Price": sv / sq,
            "Value": (sq - bq) * (sv / sq)}])], ignore_index=True)
    # --- delivery FIFO
    for _, tr in deli.iterrows():
        q, p = tr["Quantity"], tr["Price"]
        if q <= 0:
            continue
        if tr["Buy/Sell"] == "Buy":
            fifo[scrip].append([q, p])
        else:
            remaining, pnl, matched = q, 0.0, 0
            book = fifo[scrip]
            while remaining > 0 and book:
                lot = book[0]
                take = min(lot[0], remaining)
                pnl += take * (p - lot[1])
                lot[0] -= take
                remaining -= take
                matched += take
                if lot[0] == 0:
                    book.popleft()
            if matched:
                realized_rows.append((day, scrip, "delivery", matched, pnl))
            if remaining > 0:
                unmatched_sells.append((day, scrip, remaining, remaining * p))

realized = pd.DataFrame(realized_rows, columns=["Date", "Scrip", "Kind", "Qty", "GrossPnL"])
unmatched = pd.DataFrame(unmatched_sells, columns=["Date", "Scrip", "Qty", "SellValue"])


def fy_of(d):
    return f"FY{d.year}-{str(d.year + 1)[2:]}" if d.month >= 4 else f"FY{d.year - 1}-{str(d.year)[2:]}"


realized["FY"] = realized["Date"].map(fy_of)
realized.loc[realized["FY"] == "FY2026-27", "FY"] = "FY2026-27*"
trades["FYcalc"] = trades["Date"].map(fy_of)

# ------------------------------------------------------------- aggregations
fy_rows = []
for fy in TRADEBOOKS:
    s = fy_summaries[fy]
    r = realized[realized["FY"] == fy]
    gross = r["GrossPnL"].sum()
    tc = float(s["Total Trade Charges"])
    ntc = float(s["Total Non Trade Charges"])
    fy_rows.append({
        "FY": fy,
        "GrossRealizedPnL": round(gross, 2),
        "IntradayGross": round(r.loc[r["Kind"] == "intraday", "GrossPnL"].sum(), 2),
        "DeliveryGross": round(r.loc[r["Kind"] == "delivery", "GrossPnL"].sum(), 2),
        "TradeCharges": tc,
        "NonTradeCharges": ntc,
        "TotalCharges": float(s["Total Charges"]),
        "NetAfterAllCharges": round(gross - tc - ntc, 2),
        "Trades": int(s["Total Trades"]),
        "Turnover": round(trades.loc[trades["FY"] == fy, "Value"].sum(), 2),
    })
fy_table = pd.DataFrame(fy_rows)
fy_table.to_csv(os.path.join(OUT, "fy_summary.csv"), index=False)

# charges component breakdown per FY (exact, from broker summary blocks)
comp_map = {
    "Brokerage": "Brokerage", "GST": "GST", "STT": "STT", "SEBI Tax": "SEBI Tax",
    "Exchange Turnover Charges": "Exchange Turnover", "Stamp Duty": "Stamp Duty",
    "IPFT Charges": "IPFT", "DP Charges": "DP Charges",
    "Interest Charges": "Interest", "Monthly Account Maintenance": "AMC",
    "Pledge Charges": "Pledge", "Margin Shortfall Penalty": "Penalty",
}
comp_rows = []
for fy, s in fy_summaries.items():
    for k, label in comp_map.items():
        v = float(s.get(k, 0) or 0)
        if v:
            comp_rows.append({"FY": fy, "Component": label, "Amount": v})
charges_breakdown = pd.DataFrame(comp_rows)
charges_breakdown.to_csv(os.path.join(OUT, "charges_breakdown.csv"), index=False)

# monthly time series: gross realized P&L (by sell date) and trade charges
monthly_pnl = (realized.set_index("Date").groupby(pd.Grouper(freq="ME"))["GrossPnL"]
               .sum().rename("GrossPnL"))
monthly_charges = (trades.set_index("Date").groupby(pd.Grouper(freq="ME"))["TradeCharges"]
                   .sum().rename("TradeCharges"))
monthly_turnover = (trades.set_index("Date").groupby(pd.Grouper(freq="ME"))["Value"]
                    .sum().rename("Turnover"))
monthly = pd.concat([monthly_pnl, monthly_charges, monthly_turnover], axis=1).fillna(0.0)
monthly["NetPnL"] = monthly["GrossPnL"] - monthly["TradeCharges"]
monthly.to_csv(os.path.join(OUT, "monthly.csv"))

# ---------------------------------------------- broker per-scrip tables
raw = pd.read_excel(PNL_FILE, sheet_name="Equity P&L", header=None)
overall = {str(raw.iloc[i, 0]).strip(): raw.iloc[i, 1]
           for i in range(13, 27) if pd.notna(raw.iloc[i, 0])}


def read_block(start_hdr):
    cols = raw.iloc[start_hdr].tolist()
    rows = []
    for i in range(start_hdr + 1, len(raw)):
        c0 = raw.iloc[i, 0]
        if pd.isna(c0) or str(c0).strip() in ("Total", "Disclaimer"):
            break
        rows.append(raw.iloc[i].tolist())
    return pd.DataFrame(rows, columns=cols)


hdr_rows = raw.index[raw[0] == "Scrip Symbol"].tolist()
delivery_scrips = read_block(hdr_rows[0])
intraday_scrips = read_block(hdr_rows[1])
for df, ncol in [(delivery_scrips, "Net PnL"), (intraday_scrips, "Intraday PnL")]:
    for c in df.columns[2:]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

deliv_by_scrip = delivery_scrips.groupby("Scrip Symbol").agg(
    DeliveryNet=("Net PnL", "sum"), DeliveryGross=("Gross PnL", "sum"))
intra_by_scrip = intraday_scrips.groupby("Scrip Symbol").agg(
    IntradayNet=("Intraday PnL", "sum"), IntradayGross=("Gross PnL", "sum"))
scrip_total = deliv_by_scrip.join(intra_by_scrip, how="outer").fillna(0.0)
scrip_total["TotalNet"] = scrip_total["DeliveryNet"] + scrip_total["IntradayNet"]
scrip_total.sort_values("TotalNet").to_csv(os.path.join(OUT, "scrip_lifetime_pnl.csv"))

# ------------------------------------------------------------ reconciliation
print("=" * 78)
print("RECONCILIATION & RESULTS")
print("=" * 78)
print("\n--- Broker overall Equity P&L (16-Jun-2022 to 25-Aug-2026) ---")
print(f"  Gross PnL      : {float(overall['Total Gross PnL']):>12,.2f}")
print(f"  Net PnL        : {float(overall['Net PnL']):>12,.2f}")
print(f"  Intraday net   : {float(overall['Intraday Net PnL']):>12,.2f}")
print(f"  Delivery net (per-scrip total): {deliv_by_scrip['DeliveryNet'].sum():>12,.2f}")

print("\n--- Engine: per-FY realized P&L (from tradebooks) ---")
print(fy_table.to_string(index=False))

print("\n--- Cross-check vs broker app screenshot FY2026-27 (01-Apr..25-Aug-26) ---")
fy27 = fy_table[fy_table["FY"] == "FY2026-27*"].iloc[0]
print(f"  Engine gross realized : {fy27['GrossRealizedPnL']:>12,.2f}   (app shows  26,002.89)")
print(f"  File trade charges    : {fy27['TradeCharges']:>12,.2f}   (app shows  24,444.33)")
print(f"  Engine net (trade chg): {fy27['GrossRealizedPnL'] - fy27['TradeCharges']:>12,.2f}   (app shows   1,558.56)")

eng_total_gross = fy_table["GrossRealizedPnL"].sum()
print("\n--- Engine 3-FY totals vs broker lifetime ---")
print(f"  Engine gross 3 FYs    : {eng_total_gross:>12,.2f}   (broker lifetime gross 58,504.69)")
print(f"  Diff (pre-FY25 + IPO-basis gaps): {58504.69 - eng_total_gross:>10,.2f}")
if len(unmatched):
    print(f"  Unmatched sell value (no cost basis in data): "
          f"{unmatched['SellValue'].sum():,.2f} across {len(unmatched)} events")
    unmatched.to_csv(os.path.join(OUT, "unmatched_sells.csv"), index=False)

grand_net = fy_table["NetAfterAllCharges"].sum()
print("\n--- THE BOTTOM LINE (3 FYs, all charges included) ---")
print(f"  Sum of FY nets (incl. DP/AMC/interest): {grand_net:>12,.2f}")
print(f"  Broker lifetime net (trade charges only): {float(overall['Net PnL']):>10,.2f}")
ntc_total = fy_table["NonTradeCharges"].sum()
print(f"  Total non-trade charges 3 FYs: {ntc_total:>12,.2f}")
print(f"  Lifetime net incl. non-trade charges ~ "
      f"{float(overall['Net PnL']) - ntc_total:,.2f}")
print(f"  Unrealized on current holdings (app): -3,190.79")

print("\n--- Top 10 lifetime losers / winners by scrip (broker data) ---")
st = scrip_total.sort_values("TotalNet")
print(st.head(10)[["DeliveryNet", "IntradayNet", "TotalNet"]].to_string())
print(st.tail(10)[["DeliveryNet", "IntradayNet", "TotalNet"]].to_string())

print(f"\nCSV outputs written to {OUT}")
