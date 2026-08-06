"""Purged, embargoed walk-forward splits.

Two failure modes this exists to prevent:

1. **Shuffled CV on a time series.** ``train_test_split`` or ``KFold`` lets the
   model train on 2024 and test on 2019. Accuracy looks great and means nothing.
2. **Label overlap at the boundary.** With a 5-day horizon, the label for the
   last training row spans 5 days *into* the test period. The model has
   effectively seen the answer. We purge those rows (``embargo = horizon``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Fold:
    index: int
    train: np.ndarray
    test: np.ndarray


def walk_forward_splits(
    n_samples: int,
    n_splits: int = 5,
    min_train: int = 750,
    embargo: int = 1,
    expanding: bool = True,
) -> list[Fold]:
    """Chronological folds: train on the past, test on the next block, repeat.

    ``expanding=True`` grows the training window each fold (more data, but the
    model carries old regimes). ``expanding=False`` uses a rolling window of
    ``min_train`` rows, which adapts faster to regime change.
    """
    if n_samples <= min_train + n_splits:
        raise ValueError(
            f"Not enough rows ({n_samples}) for {n_splits} folds with "
            f"min_train={min_train}. Lower --min-train or widen --start."
        )

    testable = n_samples - min_train
    fold_size = testable // n_splits
    if fold_size < 5:
        raise ValueError(
            f"Fold size would be {fold_size} rows. Use fewer --splits or more history."
        )

    folds: list[Fold] = []
    for i in range(n_splits):
        test_start = min_train + i * fold_size
        test_end = n_samples if i == n_splits - 1 else test_start + fold_size
        train_end = max(0, test_start - embargo)
        train_start = 0 if expanding else max(0, train_end - min_train)
        if train_end - train_start < 50:
            continue
        folds.append(
            Fold(
                index=i,
                train=np.arange(train_start, train_end),
                test=np.arange(test_start, test_end),
            )
        )
    return folds
