"""Common data and array validation helpers across the platform."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd

from gsm_poc.data.validate import (
    FLAG_COLUMNS,
    FLOAT_COLUMNS,
    INTEGER_COLUMNS,
    STRING_COLUMNS,
    TIMESTAMP_COLUMNS,
    TLC_COLUMNS,
    tlc_schema,
    zone_lookup,
)

__all__ = [
    "FLAG_COLUMNS",
    "FLOAT_COLUMNS",
    "INTEGER_COLUMNS",
    "STRING_COLUMNS",
    "TIMESTAMP_COLUMNS",
    "TLC_COLUMNS",
    "assert_finite_numeric",
    "assert_probability_simplex",
    "parse_offset_timestamp",
    "require_probabilities",
    "tlc_schema",
    "valid_probabilities",
    "zone_lookup",
]


def assert_finite_numeric(array_or_series: Any, field_name: str = "Values") -> None:
    """Ensure data is non-empty, numeric and finite."""
    arr = np.asarray(array_or_series, dtype=float)
    if not arr.size or not np.isfinite(arr).all():
        raise ValueError(f"{field_name} must be non-empty, numeric and finite")


def parse_offset_timestamp(value: Any, timezone: str, field_name: str) -> pd.Timestamp:
    """Validate and convert an ISO string with explicit offset into UTC Timestamp."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO timestamp with an explicit offset")
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError(f"{field_name} must be an ISO timestamp with an explicit offset")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone}") from exc
    local = timestamp.tz_convert(timezone)
    if timestamp.utcoffset() != local.utcoffset():
        raise ValueError(f"{field_name} offset differs from timezone {timezone}")
    return timestamp.tz_convert("UTC")


def assert_probability_simplex(
    probabilities: np.ndarray, tol: float = 1e-10, field_name: str = "Probabilities"
) -> None:
    """Validate that probability rows lie on the unit simplex: >= 0 and sum to 1."""
    p = np.asarray(probabilities, dtype=float)
    if not np.isfinite(p).all() or (p < -tol).any() or (p > 1 + tol).any():
        raise ValueError(f"{field_name} must be finite within [0, 1]")
    row_sums = p.sum(axis=-1)
    if not np.allclose(row_sums, 1.0, atol=tol, rtol=0):
        raise ValueError(f"{field_name} rows must sum to 1.0 within tolerance {tol}")


def valid_probabilities(probabilities: np.ndarray, tolerance: float = 1e-12) -> bool:
    """Check if probability rows lie strictly on the 3-choice simplex."""
    values = np.asarray(probabilities, dtype=float)
    return bool(
        values.ndim == 2
        and values.shape[1] == 3
        and np.isfinite(values).all()
        and (values >= 0).all()
        and (values <= 1).all()
        and np.allclose(values.sum(axis=1), 1, rtol=0, atol=tolerance)
    )


def require_probabilities(probabilities: np.ndarray) -> None:
    """Assert valid probabilities, rejecting clipping."""
    if not valid_probabilities(probabilities):
        raise ValueError("Invalid X/Y/NONE probabilities; configuration is rejected, not clipped")
