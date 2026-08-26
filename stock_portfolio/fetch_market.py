"""Fetch market data for current holdings + NIFTY 50 via yfinance (free).
Tries .NS then .BO for each symbol. Writes output/market_snapshot.csv and
output/price_history.csv (daily closes, long format).
"""
import os

import pandas as pd
import yfinance as yf

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "output")
os.makedirs(OUT, exist_ok=True)

HOLDINGS = {  # symbol -> (qty, avg_cost)  from the app screenshots, 25-Aug-2026
    "ARDEE": (100, 67.18),
    "COALINDIA": (1, 416.74),
    "DHOOTTRANS": (13, 1476.34),
    "HORIZONIND": (249, 60.00),
    "LALITHAA": (50, 254.11),
    "SHIPROCKET": (150, 146.06),
}
BENCH = {"NIFTY50": "^NSEI", "NIFTY_SMALLCAP250": "^CNXSC"}

rows, hist_frames = [], []
for sym, (qty, cost) in HOLDINGS.items():
    got = None
    for suffix in (".NS", ".BO"):
        try:
            t = yf.Ticker(sym + suffix)
            h = t.history(period="1y", interval="1d", auto_adjust=True)
            if len(h) >= 5:
                got = (sym + suffix, h)
                break
        except Exception as e:
            print(f"  {sym}{suffix}: {e}")
    if got is None:
        print(f"!! no data for {sym}")
        rows.append({"Symbol": sym, "Ticker": None})
        continue
    tk, h = got
    close = h["Close"]
    last = float(close.iloc[-1])
    d50 = float(close.tail(50).mean()) if len(close) >= 50 else None
    d200 = float(close.tail(200).mean()) if len(close) >= 200 else None
    peak = float(close.max())
    r1m = last / float(close.iloc[-22]) - 1 if len(close) >= 22 else None
    r3m = last / float(close.iloc[-66]) - 1 if len(close) >= 66 else None
    rows.append({
        "Symbol": sym, "Ticker": tk, "BarsAvailable": len(close),
        "FirstBar": close.index[0].date(), "Last": round(last, 2),
        "Qty": qty, "AvgCost": cost,
        "UnrlzPct": round((last / cost - 1) * 100, 2),
        "UnrlzINR": round((last - cost) * qty, 2),
        "DMA50": round(d50, 2) if d50 else None,
        "DMA200": round(d200, 2) if d200 else None,
        "PctVs50DMA": round((last / d50 - 1) * 100, 2) if d50 else None,
        "DrawdownFromPeak": round((last / peak - 1) * 100, 2),
        "Ret1M": round(r1m * 100, 2) if r1m is not None else None,
        "Ret3M": round(r3m * 100, 2) if r3m is not None else None,
    })
    hist_frames.append(pd.DataFrame({"Date": close.index.tz_localize(None),
                                     "Symbol": sym, "Close": close.values}))

for name, tkr in BENCH.items():
    try:
        h = yf.Ticker(tkr).history(period="2y", interval="1d", auto_adjust=True)
        close = h["Close"]
        last = float(close.iloc[-1])
        # FY returns
        def ret_since(datestr):
            sub = close[close.index >= datestr]
            return (last / float(sub.iloc[0]) - 1) * 100 if len(sub) else None
        rows.append({
            "Symbol": name, "Ticker": tkr, "BarsAvailable": len(close),
            "Last": round(last, 2),
            "Ret1M": round(ret_since((close.index[-1] - pd.Timedelta(days=30)).strftime('%Y-%m-%d')), 2),
            "RetFY27td": round(ret_since("2026-04-01"), 2),
            "RetFY26": None,
        })
        fy26 = close[(close.index >= "2025-04-01") & (close.index <= "2026-03-31")]
        if len(fy26):
            rows[-1]["RetFY26"] = round((float(fy26.iloc[-1]) / float(fy26.iloc[0]) - 1) * 100, 2)
        hist_frames.append(pd.DataFrame({"Date": close.index.tz_localize(None),
                                         "Symbol": name, "Close": close.values}))
    except Exception as e:
        print(f"!! {name}: {e}")

snap = pd.DataFrame(rows)
snap.to_csv(os.path.join(OUT, "market_snapshot.csv"), index=False)
pd.concat(hist_frames).to_csv(os.path.join(OUT, "price_history.csv"), index=False)
print(snap.to_string(index=False))
