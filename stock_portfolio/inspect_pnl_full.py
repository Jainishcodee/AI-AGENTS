"""Dump the full Equity P&L sheet (all tables) and row counts of tradebooks."""
import pandas as pd

PNL = "g:/AI AGENTS/stock_portfolio/0cfdbedc-0540-4a52-8afe-c3e315871a48.xlsx"
df = pd.read_excel(PNL, sheet_name="Equity P&L", header=None)
print("TOTAL ROWS:", len(df), "COLS:", df.shape[1])
# Print column 0/1 labels for every row to find table boundaries
for i, row in df.iterrows():
    c0, c1 = row[0], row[1]
    if pd.notna(c0) and not isinstance(c0, (int, float)):
        print(i, "|", str(c0)[:60], "|", str(c1)[:40] if pd.notna(c1) else "")

for f, tag in [("f3bdcf4d-b1db-4403-8352-b82a9f3e381e", "FY25"),
               ("454ddc26-53cd-40cf-adc8-da2010eb3d90", "FY27ytd"),
               ("c991636e-4bd9-4e2e-93e8-736ec1769a92", "FY26")]:
    t = pd.read_excel(f"g:/AI AGENTS/stock_portfolio/{f}.xlsx", sheet_name="TradesAndCharges", header=None)
    print(tag, "rows:", len(t))
