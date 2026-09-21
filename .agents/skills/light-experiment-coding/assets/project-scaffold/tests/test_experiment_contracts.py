"""Gold/property/metamorphic tests for the experiment scaffold.

During scaffold construction these tests were written first and failed because
``example.experiment_contracts`` did not exist; they now preserve that contract.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from example.experiment_contracts import brier_score, fit_train_transform_test


def test_brier_score_gold_case():
    y_true = np.array([0.0, 1.0, 1.0, 0.0])
    probability = np.array([0.1, 0.8, 0.4, 0.3])
    assert brier_score(y_true, probability) == pytest.approx(0.125)


@given(
    pairs=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=1),
            st.floats(
                min_value=0.0,
                max_value=1.0,
                allow_nan=False,
                allow_infinity=False,
            ),
        ),
        min_size=1,
        max_size=50,
    )
)
def test_brier_score_is_bounded(pairs):
    y_true, probability = zip(*pairs, strict=True)
    score = brier_score(np.asarray(y_true), np.asarray(probability))
    assert 0.0 <= score <= 1.0


@given(
    pairs=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=1),
            st.floats(
                min_value=0.0,
                max_value=1.0,
                allow_nan=False,
                allow_infinity=False,
            ),
        ),
        min_size=2,
        max_size=50,
    )
)
def test_brier_score_is_permutation_invariant(pairs):
    y_true, probability = zip(*pairs, strict=True)
    y = np.asarray(y_true)
    p = np.asarray(probability)
    order = np.arange(len(y))[::-1]
    assert brier_score(y, p) == pytest.approx(brier_score(y[order], p[order]))


def test_preprocessor_fits_train_only():
    class RecordingTransformer:
        def __init__(self):
            self.fit_rows = None

        def fit(self, x):
            self.fit_rows = np.asarray(x).copy()
            return self

        def transform(self, x):
            return np.asarray(x) - self.fit_rows.mean(axis=0)

    transformer = RecordingTransformer()
    x_train = np.array([[1.0], [3.0]])
    x_test = np.array([[100.0]])

    train_out, test_out = fit_train_transform_test(transformer, x_train, x_test)

    assert np.array_equal(transformer.fit_rows, x_train)
    assert np.allclose(train_out, [[-1.0], [1.0]])
    assert np.allclose(test_out, [[98.0]])
