"""Probe the 4 Excel files: sheet names, shapes, first rows of every sheet."""
import glob

import pandas as pd

for path in sorted(glob.glob("g:/AI AGENTS/stock_portfolio/*.xlsx")):
    print("=" * 100)
    print("FILE:", path)
    try:
        xl = pd.ExcelFile(path)
        print("SHEETS:", xl.sheet_names)
        for sheet in xl.sheet_names:
            df = xl.parse(sheet, header=None, nrows=40)
            print("-" * 80)
            print(f"SHEET '{sheet}'  shape(first 40 rows): {df.shape}")
            with pd.option_context("display.max_columns", None, "display.width", 250,
                                   "display.max_colwidth", 28):
                print(df.to_string())
    except Exception as e:
        print("ERROR:", e)
