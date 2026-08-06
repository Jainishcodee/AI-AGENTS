"""Model zoo.

Hyperparameters are deliberately conservative. Daily equity returns carry a
signal-to-noise ratio somewhere near 1:50; a deep, unregularised tree ensemble
will memorise the noise and produce a beautiful in-sample curve that dies out of
sample. Shallow trees, heavy L2, high ``min_child_samples``, and column
subsampling are the defaults for a reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

LGBM_CLF_DEFAULTS: dict[str, Any] = dict(
    n_estimators=400,
    learning_rate=0.02,
    num_leaves=15,
    max_depth=4,
    min_child_samples=60,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.7,
    reg_lambda=5.0,
    reg_alpha=0.5,
    verbosity=-1,
)

LGBM_REG_DEFAULTS: dict[str, Any] = dict(LGBM_CLF_DEFAULTS, objective="huber")


@dataclass
class ModelSpec:
    name: str = "lgbm"
    task: str = "classification"
    params: dict[str, Any] = field(default_factory=dict)
    seed: int = 42


def build_model(spec: ModelSpec):
    clf = spec.task == "classification"
    name = spec.name.lower()

    if name == "lgbm":
        import lightgbm as lgb

        base = LGBM_CLF_DEFAULTS if clf else LGBM_REG_DEFAULTS
        params = {**base, "random_state": spec.seed, **spec.params}
        return (lgb.LGBMClassifier if clf else lgb.LGBMRegressor)(**params)

    if name == "logistic":
        if not clf:
            raise ValueError("'logistic' is a classifier; use 'ridge' for regression")
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("model", LogisticRegression(C=0.1, max_iter=2000, random_state=spec.seed)),
            ]
        )

    if name == "ridge":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("model", Ridge(alpha=10.0, random_state=spec.seed)),
            ]
        )

    if name == "rf":
        params = dict(
            n_estimators=400,
            max_depth=6,
            min_samples_leaf=50,
            max_features="sqrt",
            n_jobs=-1,
            random_state=spec.seed,
            **spec.params,
        )
        model = (RandomForestClassifier if clf else RandomForestRegressor)(**params)
        return Pipeline([("impute", SimpleImputer(strategy="median")), ("model", model)])

    if name == "dummy":
        # "Always predict the majority class" -- the bar every model must clear.
        return (
            DummyClassifier(strategy="prior")
            if clf
            else DummyRegressor(strategy="mean")
        )

    raise ValueError(f"unknown model {spec.name!r} (lgbm|logistic|ridge|rf|dummy)")


def predict_score(model, X) -> np.ndarray:
    """Uniform accessor: P(up) for classifiers, raw prediction for regressors."""
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(X))[:, 1]
    return np.asarray(model.predict(X), dtype="float64")


def feature_importance(model, columns: list[str]) -> dict[str, float]:
    est = model
    if isinstance(model, Pipeline):
        est = model.named_steps.get("model", model)
    if hasattr(est, "feature_importances_"):
        vals = np.asarray(est.feature_importances_, dtype="float64")
    elif hasattr(est, "coef_"):
        vals = np.abs(np.asarray(est.coef_, dtype="float64")).ravel()
    else:
        return {}
    if len(vals) != len(columns):
        return {}
    total = vals.sum()
    if total > 0:
        vals = vals / total
    return dict(zip(columns, vals))
