"""Feature engineering.

Every feature on row ``t`` is computed only from data up to and including the
close of day ``t``. Nothing here calls ``.shift(-n)``, ``center=True``, or any
other backwards-looking window -- that is the single rule that keeps a backtest
from being a fantasy, and ``tests/test_features.py`` enforces it mechanically.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RETURN_HORIZONS = (1, 2, 3, 5, 10, 21, 63)
VOL_WINDOWS = (5, 10, 21, 63)
SMA_WINDOWS = (10, 20, 50, 200)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


def _zscore(s: pd.Series, window: int) -> pd.Series:
    mean = s.rolling(window).mean()
    std = s.rolling(window).std()
    return (s - mean) / std.replace(0.0, np.nan)


def build_features(df: pd.DataFrame, benchmark: pd.DataFrame | None = None) -> pd.DataFrame:
    """Turn an OHLCV frame into a model-ready feature matrix.

    Features are deliberately scale-free (ratios, z-scores, percentiles) so a
    model trained across price regimes -- or transferred between tickers --
    is not keying on the absolute rupee/dollar level of the stock.
    """
    o, h, l, c, v = (df["Open"], df["High"], df["Low"], df["Close"], df["Volume"])
    ret1 = c.pct_change()
    f = pd.DataFrame(index=df.index)

    # --- momentum / trend -------------------------------------------------
    for n in RETURN_HORIZONS:
        f[f"ret_{n}d"] = c.pct_change(n)
    # Classic 12-1 momentum: last year excluding the most recent month, which
    # is where short-term reversal lives.
    f["mom_12_1"] = c.shift(21) / c.shift(252) - 1.0

    for n in SMA_WINDOWS:
        sma = c.rolling(n).mean()
        f[f"px_over_sma{n}"] = c / sma - 1.0
    f["sma10_over_sma50"] = c.rolling(10).mean() / c.rolling(50).mean() - 1.0
    f["sma50_over_sma200"] = c.rolling(50).mean() / c.rolling(200).mean() - 1.0

    macd_line, macd_sig, macd_hist = macd(c)
    f["macd"] = macd_line / c
    f["macd_hist"] = macd_hist / c

    # --- mean reversion / oscillators -------------------------------------
    f["rsi_14"] = rsi(c, 14) / 100.0
    f["rsi_5"] = rsi(c, 5) / 100.0
    bb_mid = c.rolling(20).mean()
    bb_std = c.rolling(20).std()
    f["bb_pctb"] = (c - bb_mid) / (2.0 * bb_std).replace(0.0, np.nan)
    f["bb_width"] = (4.0 * bb_std) / bb_mid
    f["ret1_z_21"] = _zscore(ret1, 21)

    # --- volatility & risk shape ------------------------------------------
    for n in VOL_WINDOWS:
        f[f"vol_{n}d"] = ret1.rolling(n).std()
    f["vol_ratio_5_63"] = f["vol_5d"] / f["vol_63d"].replace(0.0, np.nan)
    f["atr_14"] = atr(h, l, c, 14) / c
    f["skew_63"] = ret1.rolling(63).skew()
    f["kurt_63"] = ret1.rolling(63).kurt()
    roll_max = c.rolling(252, min_periods=63).max()
    f["drawdown_252"] = c / roll_max - 1.0
    f["pct_rank_252"] = c.rolling(252, min_periods=63).rank(pct=True)

    # --- intraday structure ------------------------------------------------
    rng = (h - l).replace(0.0, np.nan)
    f["close_loc"] = (c - l) / rng            # where in the day's range we closed
    f["hl_range"] = rng / c
    f["gap_open"] = o / c.shift(1) - 1.0
    f["body"] = (c - o) / c

    # --- volume ------------------------------------------------------------
    f["vol_z_21"] = _zscore(v, 21)
    f["vol_over_ma20"] = v / v.rolling(20).mean().replace(0.0, np.nan)
    obv = (np.sign(ret1).fillna(0.0) * v).cumsum()
    f["obv_slope_20"] = obv.diff(20) / v.rolling(20).mean().replace(0.0, np.nan) / 20.0
    # Dollar/rupee volume trend -- a liquidity regime proxy.
    f["turnover_z_63"] = _zscore(c * v, 63)

    # --- calendar (cheap, and genuinely predictive at the margin) ----------
    f["dow"] = df.index.dayofweek.astype("float64")
    f["month"] = df.index.month.astype("float64")
    f["day_of_month"] = df.index.day.astype("float64")

    # --- benchmark-relative -------------------------------------------------
    if benchmark is not None and "Close" in benchmark:
        bc = benchmark["Close"].reindex(df.index).ffill()
        bret1 = bc.pct_change()
        for n in (1, 5, 21, 63):
            f[f"bench_ret_{n}d"] = bc.pct_change(n)
            f[f"rel_str_{n}d"] = c.pct_change(n) - bc.pct_change(n)
        f["bench_vol_21d"] = bret1.rolling(21).std()
        f["beta_63"] = (
            ret1.rolling(63).cov(bret1) / bret1.rolling(63).var().replace(0.0, np.nan)
        )
        f["bench_px_over_sma50"] = bc / bc.rolling(50).mean() - 1.0

    return f.replace([np.inf, -np.inf], np.nan)


def feature_columns(f: pd.DataFrame) -> list[str]:
    return [c for c in f.columns if not c.startswith("_")]
