"""Minimal data/metric contracts for leakage-safe experiment implementations."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, TypeVar

import numpy as np
from numpy.typing import ArrayLike, NDArray


class Transformer(Protocol):
    """Smallest preprocessing interface needed by the scaffold."""

    def fit(self, x: ArrayLike) -> "Transformer": ...

    def transform(self, x: ArrayLike) -> NDArray[np.floating]: ...


class DatasetLoader(Protocol):
    """Load a frozen data revision and return patient/entity identifiers too."""

    def load(
        self,
    ) -> tuple[NDArray[np.floating], NDArray[np.integer], NDArray[Any]]: ...


class ProbabilisticModel(Protocol):
    """Small model boundary used by train/eval orchestration."""

    def fit(self, x: ArrayLike, y: ArrayLike) -> "ProbabilisticModel": ...

    def predict_proba(self, x: ArrayLike) -> NDArray[np.floating]: ...


class Metric(Protocol):
    """Named metric boundary; metadata is serialized into raw metric rows."""

    name: str

    def __call__(self, y_true: ArrayLike, prediction: ArrayLike) -> float: ...

    def metadata(self) -> Mapping[str, Any]: ...


T = TypeVar("T", bound=Transformer)


def fit_train_transform_test(
    transformer: T,
    x_train: ArrayLike,
    x_test: ArrayLike,
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """Fit only on training observations, then transform train and test.

    Keep the split outside this function. Passing the unsplit dataset as
    ``x_train`` is a caller error and must be caught by split/provenance tests.
    """
    transformer.fit(x_train)
    train_out = np.asarray(transformer.transform(x_train), dtype=float)
    test_out = np.asarray(transformer.transform(x_test), dtype=float)
    if not np.isfinite(train_out).all() or not np.isfinite(test_out).all():
        raise ValueError("preprocessing produced NaN or Inf")
    return train_out, test_out


def brier_score(y_true: ArrayLike, probability: ArrayLike) -> float:
    """Return binary Brier loss after strict shape/range/finite validation."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probability, dtype=float)
    if y.ndim != 1 or p.ndim != 1 or y.shape != p.shape or y.size == 0:
        raise ValueError(
            "y_true and probability must be non-empty 1D arrays of equal length"
        )
    if not np.isfinite(y).all() or not np.isfinite(p).all():
        raise ValueError("inputs contain NaN or Inf")
    if not np.isin(y, (0.0, 1.0)).all():
        raise ValueError("y_true must contain only 0/1")
    if ((p < 0.0) | (p > 1.0)).any():
        raise ValueError("probability must stay in [0, 1]")
    return float(np.mean(np.square(p - y)))
