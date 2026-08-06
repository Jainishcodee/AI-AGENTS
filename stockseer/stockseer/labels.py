"""Target construction.

The label for row ``t`` is a *forward* quantity: what happens between the close
of day ``t`` and the close of day ``t+horizon``. The last ``horizon`` rows
therefore have no label and are dropped from training -- they are exactly the
rows we want to predict on.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def forward_return(close: pd.Series, horizon: int = 1) -> pd.Series:
    """Simple return from close[t] to close[t+horizon]."""
    return close.shift(-horizon) / close - 1.0


def forward_vol_adjusted(close: pd.Series, horizon: int = 1, vol_window: int = 21) -> pd.Series:
    """Forward return scaled by trailing volatility.

    Regressing on raw returns lets a handful of crisis days dominate the loss.
    Dividing by volatility *known as of t* keeps the target comparable across
    calm and violent regimes without leaking the future.
    """
    fwd = forward_return(close, horizon)
    vol = close.pct_change().rolling(vol_window).std() * np.sqrt(horizon)
    return fwd / vol.replace(0.0, np.nan)


def make_label(
    close: pd.Series,
    horizon: int = 1,
    task: str = "classification",
    deadband: float = 0.0,
) -> tuple[pd.Series, pd.Series]:
    """Return ``(y, fwd_ret)``.

    ``deadband`` (in return units, e.g. 0.002 = 20bps) drops near-flat moves from
    the training set entirely. Those rows are pure noise for a direction model:
    forcing a label on a +0.01% day teaches the model nothing except to fit the
    residual. They stay in the backtest, they just do not train.
    """
    fwd = forward_return(close, horizon)
    if task == "classification":
        y = (fwd > 0).astype("float64")
        if deadband > 0:
            y = y.where(fwd.abs() >= deadband, np.nan)
    elif task == "regression":
        y = forward_vol_adjusted(close, horizon)
    else:
        raise ValueError(f"unknown task {task!r} (use 'classification' or 'regression')")
    y = y.where(fwd.notna())
    return y, fwd


def align(
    features: pd.DataFrame, y: pd.Series, fwd: pd.Series
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Drop rows where features are still warming up or the label is missing."""
    mask = features.notna().all(axis=1) & y.notna() & fwd.notna()
    return features.loc[mask], y.loc[mask], fwd.loc[mask]
