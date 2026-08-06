"""End-to-end glue: prices -> features -> labels -> walk-forward -> report."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .backtest import (
    build_positions,
    classification_metrics,
    regression_metrics,
    simulate,
    strategy_report,
    walk_forward_predict,
)
from .data import load_benchmark, load_prices
from .features import build_features
from .labels import align, make_label
from .models import ModelSpec, build_model, feature_importance, predict_score

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"


@dataclass
class Config:
    ticker: str = "^NSEI"
    benchmark: str | None = None
    start: str = "2012-01-01"
    end: str | None = None
    horizon: int = 1
    task: str = "classification"
    deadband: float = 0.0
    model: str = "lgbm"
    params: dict[str, Any] = field(default_factory=dict)
    n_splits: int = 5
    min_train: int = 750
    expanding: bool = True
    threshold: float = 0.5
    mode: str = "long_flat"
    cost_bps: float = 5.0
    seed: int = 42
    refresh: bool = False

    @property
    def spec(self) -> ModelSpec:
        return ModelSpec(name=self.model, task=self.task, params=self.params, seed=self.seed)


@dataclass
class Dataset:
    prices: pd.DataFrame
    X: pd.DataFrame
    y: pd.Series
    fwd: pd.Series
    features_raw: pd.DataFrame


def build_dataset(cfg: Config) -> Dataset:
    prices = load_prices(cfg.ticker, start=cfg.start, end=cfg.end, refresh=cfg.refresh)

    bench = None
    if cfg.benchmark and cfg.benchmark != cfg.ticker:
        try:
            bench = load_benchmark(
                cfg.benchmark, prices.index, start=cfg.start, end=cfg.end, refresh=cfg.refresh
            )
        except Exception as exc:  # a missing benchmark should degrade, not crash
            log.warning("benchmark %s unavailable (%s); continuing without it", cfg.benchmark, exc)

    feats = build_features(prices, benchmark=bench)
    y, fwd = make_label(prices["Close"], cfg.horizon, cfg.task, cfg.deadband)
    X, y, fwd = align(feats, y, fwd)

    log.info(
        "dataset: %d rows x %d features, %s .. %s",
        len(X), X.shape[1], X.index[0].date(), X.index[-1].date(),
    )
    return Dataset(prices=prices, X=X, y=y, fwd=fwd, features_raw=feats)


def run_backtest(cfg: Config) -> dict[str, Any]:
    ds = build_dataset(cfg)
    wf = walk_forward_predict(
        ds.X,
        ds.y,
        ds.fwd,
        cfg.spec,
        n_splits=cfg.n_splits,
        min_train=cfg.min_train,
        embargo=cfg.horizon,
        expanding=cfg.expanding,
    )

    metrics = (
        classification_metrics(wf.predictions)
        if cfg.task == "classification"
        else regression_metrics(wf.predictions)
    )

    positions = build_positions(
        wf.predictions, cfg.task, cfg.threshold, cfg.mode, smooth=cfg.horizon
    )
    sim = simulate(wf.predictions, ds.prices["Close"], positions, cfg.cost_bps)
    strategy = strategy_report(sim, cfg.cost_bps)

    # Same pipeline, but with the labels shuffled: any "edge" that survives this
    # is coming from the backtest machinery, not the data.
    return {
        "config": asdict(cfg),
        "period": {
            "train_start": str(ds.X.index[0].date()),
            "test_start": str(wf.predictions.index[0].date()),
            "test_end": str(wf.predictions.index[-1].date()),
            "n_features": int(ds.X.shape[1]),
            "n_test_days": int(len(wf.predictions)),
        },
        "metrics": metrics,
        "strategy": strategy,
        "importance": wf.importance,
        "predictions": wf.predictions,
        "sim": sim,
        "dataset": ds,
        "walk_forward": wf,
    }


def shuffled_control(cfg: Config, ds: Dataset | None = None) -> dict[str, float]:
    """Null test: re-run walk-forward with the target randomly permuted.

    A correct pipeline scores ~50% accuracy / ~0.5 AUC here. Anything materially
    above that means information is leaking between features and labels, and the
    real backtest number cannot be trusted.
    """
    ds = ds or build_dataset(cfg)
    rng = np.random.default_rng(cfg.seed)
    y_shuf = pd.Series(rng.permutation(ds.y.to_numpy()), index=ds.y.index)
    wf = walk_forward_predict(
        ds.X, y_shuf, ds.fwd, cfg.spec,
        n_splits=cfg.n_splits, min_train=cfg.min_train,
        embargo=cfg.horizon, expanding=cfg.expanding,
    )
    return (
        classification_metrics(wf.predictions)
        if cfg.task == "classification"
        else regression_metrics(wf.predictions)
    )


def train_final(cfg: Config, out_dir: Path | None = None) -> Path:
    """Fit on all available history and persist the model for live prediction."""
    import joblib

    ds = build_dataset(cfg)
    model = build_model(cfg.spec)
    model.fit(ds.X, ds.y.to_numpy(dtype="float64"))

    out_dir = Path(out_dir or ARTIFACTS)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{cfg.ticker.replace('^', 'idx-')}__{cfg.model}__h{cfg.horizon}.joblib"
    joblib.dump(
        {
            "model": model,
            "columns": list(ds.X.columns),
            "config": asdict(cfg),
            "trained_through": str(ds.X.index[-1].date()),
            "trained_at": date.today().isoformat(),
            "importance": feature_importance(model, list(ds.X.columns)),
        },
        path,
    )
    log.info("saved model -> %s", path)
    return path


def predict_latest(cfg: Config, model_path: Path | str | None = None) -> dict[str, Any]:
    """Score the most recent bar. Trains on the fly if no saved model is given."""
    import joblib

    ds = build_dataset(cfg)
    if model_path:
        bundle = joblib.load(model_path)
        model, columns = bundle["model"], bundle["columns"]
        trained_through = bundle.get("trained_through")
    else:
        model = build_model(cfg.spec)
        model.fit(ds.X, ds.y.to_numpy(dtype="float64"))
        columns, trained_through = list(ds.X.columns), str(ds.X.index[-1].date())

    # The newest rows have no label yet -- which is exactly why we predict on
    # them -- so score the raw feature frame, not the label-aligned one.
    live = ds.features_raw.reindex(columns=columns)
    live = live[live.notna().all(axis=1)]
    if live.empty:
        raise ValueError("No complete feature row available for prediction.")

    row = live.iloc[[-1]]
    score = float(predict_score(model, row)[0])
    asof = row.index[-1]

    if cfg.task == "classification":
        if score > cfg.threshold:
            signal = "LONG"
        elif cfg.mode == "long_short" and score < 1.0 - cfg.threshold:
            signal = "SHORT"
        else:
            signal = "FLAT"
    else:
        signal = "LONG" if score > cfg.threshold else ("SHORT" if score < -cfg.threshold else "FLAT")

    return {
        "ticker": cfg.ticker,
        "as_of": str(asof.date()),
        "last_close": float(ds.prices["Close"].loc[asof]),
        "horizon_days": cfg.horizon,
        "score": score,
        "signal": signal,
        "trained_through": trained_through,
        "stale_bars": int((ds.prices.index[-1] - asof).days),
    }


def save_results(result: dict[str, Any], out_dir: Path | str = ARTIFACTS) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{result['config']['ticker'].replace('^', 'idx-')}__{result['config']['model']}__h{result['config']['horizon']}"

    paths = {}
    summary = {k: result[k] for k in ("config", "period", "metrics", "strategy", "importance")}
    if "shuffled_control" in result:
        summary["shuffled_control"] = result["shuffled_control"]
    paths["summary"] = out_dir / f"{tag}__summary.json"
    paths["summary"].write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    paths["sim"] = out_dir / f"{tag}__daily.csv"
    result["sim"].to_csv(paths["sim"])
    return paths
