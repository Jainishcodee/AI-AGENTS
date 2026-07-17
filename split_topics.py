"""Re-open the existing Excel, add a tab per topic with that topic's reels."""
import pandas as pd
from openpyxl import load_workbook

PATH = r"g:\AI AGENTS\instagram_saved_report.xlsx"

# Read the All Saved Reels sheet
all_df = pd.read_excel(PATH, sheet_name="All Saved Reels")

# Drop any existing topic tabs to keep this idempotent
wb = load_workbook(PATH)
core = {"All Saved Reels", "By Topic", "Top Creators", "Top Hashtags",
        "Saved by Month", "Collections", "Saved Music"}
for name in list(wb.sheetnames):
    if name not in core:
        del wb[name]
wb.save(PATH)

# Excel sheet names: max 31 chars, no [ ] : * ? / \
def clean(name):
    n = name.replace("/", "-").replace("\\", "-")
    for ch in "[]:*?":
        n = n.replace(ch, "")
    return n[:31]

with pd.ExcelWriter(PATH, engine="openpyxl", mode="a",
                    if_sheet_exists="overlay") as xl:
    # write topics ordered by reel count (skip "Other" — already in main sheet)
    counts = all_df["Topic"].value_counts()
    for topic, n in counts.items():
        sheet = clean(topic)
        sub = all_df[all_df["Topic"] == topic].copy()
        sub.to_excel(xl, sheet_name=sheet, index=False)
    # widen
    for ws in xl.book.worksheets:
        if ws.title in core: continue
        for col in ws.columns:
            width = min(60, max((len(str(c.value)) for c in col if c.value), default=10) + 2)
            ws.column_dimensions[col[0].column_letter].width = width

print(f"Added {len(counts)} topic tabs to {PATH}")
for t, n in counts.items():
    print(f"  {n:>4}  {clean(t)}")
