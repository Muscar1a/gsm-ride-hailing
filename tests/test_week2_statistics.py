from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

script_path = Path(__file__).resolve().parents[1] / "scripts/review_week2_statistics.py"
spec = importlib.util.spec_from_file_location("week2_statistics_review", script_path)
assert spec is not None and spec.loader is not None
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


@pytest.mark.parametrize(
    ("successes", "trials", "expected"),
    [
        (0, 0, (float("nan"), float("nan"))),
        (0, 10, (0.0, 0.3084971078187608)),
        (10, 10, (0.6915028921812392, 1.0)),
        (86, 100, (0.7762720186294195, 0.9212945950730457)),
    ],
)
def test_exact_interval_includes_boundaries(successes: int, trials: int, expected: tuple) -> None:
    np.testing.assert_allclose(
        review.exact_interval(successes, trials), expected, atol=1e-11, rtol=0, equal_nan=True
    )


def test_holm_preserves_original_order_and_monotonic_step_down() -> None:
    np.testing.assert_allclose(
        review.holm_adjust(np.array([0.03, 0.001, 0.04, 0.009])),
        [0.06, 0.004, 0.06, 0.027],
        rtol=0,
        atol=1e-15,
    )


@pytest.mark.parametrize("p_values", [[], [float("nan")], [-0.1], [1.1]])
def test_holm_rejects_invalid_family(p_values: list[float]) -> None:
    with pytest.raises(ValueError):
        review.holm_adjust(np.asarray(p_values))
