"""Session-aware intraday indicators.

The daily model's rule applies here too and is easier to break: everything at bar
``t`` uses only bars up to and including ``t``. Two intraday-specific traps:

* **VWAP and opening range must reset every session.** Carrying yesterday's VWAP
  into today produces a beautiful, meaningless line.
* **The opening range does not exist until it is complete.** Marking a 09:20 bar
  with the 09:15-09:30 range means the signal knew the next ten minutes. That is
  the single most common intraday backtest leak, and ``_opening_range`` refuses
  to emit a level before the window closes.
"""

from __future__ import annotations

from datetime import time

import numpy as np
import pandas as pd

SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)


def session_id(index: pd.DatetimeIndex) -> pd.Series:
    """One id per trading day, so indicators can be grouped and reset."""
    return pd.Series(index.date, index=index, name="session")


def typical_price(df: pd.DataFrame) -> pd.Series:
    return (df["High"] + df["Low"] + df["Close"]) / 3.0


def vwap(df: pd.DataFrame) -> pd.Series:
    """Volume-weighted average price, reset each session."""
    sess = session_id(df.index)
    tp = typical_price(df)
    pv = (tp * df["Volume"]).groupby(sess).cumsum()
    vol = df["Volume"].groupby(sess).cumsum()
    return (pv / vol.replace(0.0, np.nan)).rename("vwap")


def vwap_bands(df: pd.DataFrame, mult: float = 1.0) -> pd.DataFrame:
    """VWAP plus/minus a running standard deviation of price around it."""
    sess = session_id(df.index)
    vw = vwap(df)
    dev = (typical_price(df) - vw) ** 2
    var = dev.groupby(sess).expanding().mean().reset_index(level=0, drop=True)
    sd = np.sqrt(var)
    return pd.DataFrame({"vwap": vw, "upper": vw + mult * sd, "lower": vw - mult * sd})


def _opening_range(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """High/low of the first ``minutes`` of each session.

    NaN until the window has closed. A level you could not have known is not a
    level -- emitting it early is how an intraday backtest invents an edge.
    """
    out = pd.DataFrame(index=df.index, columns=["or_high", "or_low"], dtype="float64")
    for _, day in df.groupby(session_id(df.index), sort=False):
        start = day.index[0]
        cutoff = start + pd.Timedelta(minutes=minutes)
        window = day[day.index < cutoff]
        if window.empty:
            continue
        hi, lo = float(window["High"].max()), float(window["Low"].min())
        established = day.index[day.index >= cutoff]
        out.loc[established, "or_high"] = hi
        out.loc[established, "or_low"] = lo
    return out


def opening_range(df: pd.DataFrame, minutes: int = 15) -> pd.DataFrame:
    return _opening_range(df, minutes)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average true range on intraday bars, not carried across the overnight gap."""
    sess = session_id(df.index)
    prev_close = df["Close"].groupby(sess).shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean().rename("atr")


def relative_volume(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """Volume against its own recent average -- the cleanest conviction proxy."""
    avg = df["Volume"].rolling(lookback).mean()
    return (df["Volume"] / avg.replace(0.0, np.nan)).rename("rvol")


def minutes_since_open(index: pd.DatetimeIndex) -> pd.Series:
    """Time of day matters intraday: the open and close behave differently."""
    mins = index.hour * 60 + index.minute
    return pd.Series(mins - (SESSION_OPEN.hour * 60 + SESSION_OPEN.minute),
                     index=index, name="mins_open")


def enrich(df: pd.DataFrame, or_minutes: int = 15) -> pd.DataFrame:
    """Attach every intraday indicator the rules need, in one pass."""
    out = df.copy()
    bands = vwap_bands(out)
    out["vwap"] = bands["vwap"]
    out["vwap_upper"] = bands["upper"]
    out["vwap_lower"] = bands["lower"]
    out = out.join(opening_range(out, or_minutes))
    out["atr"] = atr(out)
    out["rvol"] = relative_volume(out)
    out["mins_open"] = minutes_since_open(out.index)
    out["ema9"] = out["Close"].ewm(span=9, adjust=False).mean()
    out["ema21"] = out["Close"].ewm(span=21, adjust=False).mean()
    out["above_vwap"] = out["Close"] > out["vwap"]
    return out
