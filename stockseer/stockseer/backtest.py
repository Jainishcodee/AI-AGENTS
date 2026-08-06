"""Walk-forward evaluation and strategy simulation.

Two separate questions, deliberately reported separately:

* **Is there signal?** -- accuracy, AUC, Brier, log loss vs. the naive baseline.
* **Is it worth trading?** -- net-of-cost equity vs. buy-and-hold.

They come apart constantly. A model with 52% accuracy can still lose money after
costs; a model with 50.5% accuracy that is right on the big days can beat the
index. Neither number alone tells you anything.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    roc_auc_score,
)

from .models import ModelSpec, build_model, feature_importance, predict_score
from .splits import Fold, walk_forward_splits

log = logging.getLogger(__name__)

TRADING_DAYS = 252


# --------------------------------------------------------------------------- #
# Out-of-sample prediction
# --------------------------------------------------------------------------- #
@dataclass
class WalkForwardResult:
    predictions: pd.DataFrame          # index=date, cols: score, y, fwd_ret, fold
    folds: list[Fold]
    importance: dict[str, float]
    spec: ModelSpec
    columns: list[str] = field(default_factory=list)


def walk_forward_predict(
    X: pd.DataFrame,
    y: pd.Series,
    fwd: pd.Series,
    spec: ModelSpec,
    n_splits: int = 5,
    min_train: int = 750,
    embargo: int = 1,
    expanding: bool = True,
) -> WalkForwardResult:
    folds = walk_forward_splits(
        len(X), n_splits=n_splits, min_train=min_train, embargo=embargo, expanding=expanding
    )
    # Fit on DataFrames, not arrays: LightGBM and sklearn both carry the column
    # names through, so importances stay labelled and a column-order mismatch at
    # predict time raises instead of silently scoring the wrong feature.
    yv = y.to_numpy(dtype="float64")
    rows, importances = [], []

    for fold in folds:
        model = build_model(spec)
        model.fit(X.iloc[fold.train], yv[fold.train])
        score = predict_score(model, X.iloc[fold.test])
        rows.append(
            pd.DataFrame(
                {
                    "score": score,
                    "y": yv[fold.test],
                    "fwd_ret": fwd.to_numpy()[fold.test],
                    "fold": fold.index,
                },
                index=X.index[fold.test],
            )
        )
        imp = feature_importance(model, list(X.columns))
        if imp:
            importances.append(imp)
        log.info(
            "fold %d: train %s..%s (%d) -> test %s..%s (%d)",
            fold.index,
            X.index[fold.train[0]].date(),
            X.index[fold.train[-1]].date(),
            len(fold.train),
            X.index[fold.test[0]].date(),
            X.index[fold.test[-1]].date(),
            len(fold.test),
        )

    preds = pd.concat(rows).sort_index()
    mean_imp = (
        pd.DataFrame(importances).mean().sort_values(ascending=False).to_dict()
        if importances
        else {}
    )
    return WalkForwardResult(preds, folds, mean_imp, spec, list(X.columns))


# --------------------------------------------------------------------------- #
# Statistical metrics
# --------------------------------------------------------------------------- #
def classification_metrics(preds: pd.DataFrame) -> dict[str, float]:
    y, s = preds["y"].to_numpy(), preds["score"].to_numpy()
    yhat = (s > 0.5).astype("float64")
    base_rate = float(y.mean())
    out = {
        "n": float(len(y)),
        "base_rate_up": base_rate,
        "baseline_accuracy": max(base_rate, 1 - base_rate),
        "accuracy": float(accuracy_score(y, yhat)),
        "brier": float(brier_score_loss(y, np.clip(s, 1e-6, 1 - 1e-6))),
        "log_loss": float(log_loss(y, np.clip(s, 1e-6, 1 - 1e-6), labels=[0.0, 1.0])),
    }
    out["auc"] = float(roc_auc_score(y, s)) if len(np.unique(y)) > 1 else float("nan")
    out["edge_vs_baseline"] = out["accuracy"] - out["baseline_accuracy"]
    # Binomial standard error of the accuracy estimate. If the edge is smaller
    # than ~2 of these, it is not distinguishable from luck.
    out["accuracy_se"] = float(np.sqrt(0.25 / len(y)))
    out["edge_t_stat"] = out["edge_vs_baseline"] / out["accuracy_se"]
    return out


def regression_metrics(preds: pd.DataFrame) -> dict[str, float]:
    y, s = preds["y"].to_numpy(), preds["score"].to_numpy()
    ss_res = float(((y - s) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "n": float(len(y)),
        "mae": float(mean_absolute_error(y, s)),
        "r2_oos": 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
        "ic_pearson": float(np.corrcoef(s, y)[0, 1]),
        "ic_spearman": float(pd.Series(s).corr(pd.Series(y), method="spearman")),
        "direction_accuracy": float(((s > 0) == (y > 0)).mean()),
    }


# --------------------------------------------------------------------------- #
# Strategy simulation
# --------------------------------------------------------------------------- #
def build_positions(
    preds: pd.DataFrame,
    task: str,
    threshold: float = 0.5,
    mode: str = "long_flat",
    smooth: int = 1,
) -> pd.Series:
    """Map model scores to a position in [-1, 1] held from close t to close t+1.

    ``smooth`` averages the last ``n`` days of signal. For a horizon > 1 this is
    the standard overlapping-position construction: each day you roll 1/n of the
    book, so a 5-day view does not pretend to be a 1-day round trip.
    """
    s = preds["score"]
    if task == "classification":
        long_sig, short_sig = s > threshold, s < (1.0 - threshold)
    else:
        long_sig, short_sig = s > threshold, s < -threshold

    pos = pd.Series(0.0, index=s.index)
    pos[long_sig] = 1.0
    if mode == "long_short":
        pos[short_sig] = -1.0
    elif mode != "long_flat":
        raise ValueError(f"unknown mode {mode!r} (long_flat|long_short)")

    if smooth > 1:
        pos = pos.rolling(smooth, min_periods=1).mean()
    return pos


def simulate(
    preds: pd.DataFrame,
    close: pd.Series,
    positions: pd.Series,
    cost_bps: float = 5.0,
) -> pd.DataFrame:
    """Daily mark-to-market of the strategy against buy-and-hold.

    Position ``pos_t`` is decided from information at the close of ``t`` and
    earns the close-to-close return of ``t+1``. Costs are charged on the
    *change* in position, so a held position is free and a flip costs double.
    """
    ret_next = (close.pct_change().shift(-1)).reindex(preds.index)
    pos = positions.reindex(preds.index).fillna(0.0)
    turnover = pos.diff().abs().fillna(pos.abs())
    cost = turnover * (cost_bps / 10_000.0)

    gross = pos * ret_next
    net = gross - cost
    out = pd.DataFrame(
        {
            "score": preds["score"],
            "position": pos,
            "market_ret": ret_next,
            "gross_ret": gross,
            "cost": cost,
            "strategy_ret": net,
            "turnover": turnover,
        }
    ).dropna(subset=["market_ret"])
    out["strategy_equity"] = (1.0 + out["strategy_ret"]).cumprod()
    out["market_equity"] = (1.0 + out["market_ret"]).cumprod()
    return out


def _drawdown(equity: pd.Series) -> pd.Series:
    return equity / equity.cummax() - 1.0


def performance_stats(rets: pd.Series, equity: pd.Series | None = None) -> dict[str, float]:
    rets = rets.dropna()
    if rets.empty:
        return {}
    equity = (1.0 + rets).cumprod() if equity is None else equity
    years = len(rets) / TRADING_DAYS
    total = float(equity.iloc[-1] - 1.0)
    ann_vol = float(rets.std() * np.sqrt(TRADING_DAYS))
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 else float("nan")
    downside = rets[rets < 0].std() * np.sqrt(TRADING_DAYS)
    dd = _drawdown(equity)
    # Hit rate over *active* days only. Counting flat days as losses would let a
    # strategy that sits in cash half the time look like it is wrong half the
    # time, which is a different claim entirely.
    active = rets[rets != 0.0]
    return {
        "total_return": total,
        "cagr": cagr,
        "ann_vol": ann_vol,
        "sharpe": float(rets.mean() / rets.std() * np.sqrt(TRADING_DAYS)) if rets.std() > 0 else float("nan"),
        "sortino": float(rets.mean() * TRADING_DAYS / downside) if downside and downside > 0 else float("nan"),
        "max_drawdown": float(dd.min()),
        "calmar": float(cagr / abs(dd.min())) if dd.min() < 0 else float("nan"),
        "hit_rate": float((active > 0).mean()) if len(active) else float("nan"),
        "active_days": float(len(active)),
        "days": float(len(rets)),
    }


def strategy_report(sim: pd.DataFrame, cost_bps: float) -> dict[str, Any]:
    strat = performance_stats(sim["strategy_ret"], sim["strategy_equity"])
    market = performance_stats(sim["market_ret"], sim["market_equity"])
    exposure = float(sim["position"].abs().mean())
    return {
        "strategy": strat,
        "buy_and_hold": market,
        "excess_return": strat.get("total_return", 0.0) - market.get("total_return", 0.0),
        "excess_cagr": strat.get("cagr", 0.0) - market.get("cagr", 0.0),
        "avg_exposure": exposure,
        "ann_turnover": float(sim["turnover"].sum() / len(sim) * TRADING_DAYS),
        "total_cost_drag": float(sim["cost"].sum()),
        "cost_bps": cost_bps,
    }
