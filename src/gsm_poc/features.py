"""Fixed taxonomy encoding, observed-only inputs and date-grouped folds."""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from gsm_poc.config import Config

FEATURE_COLUMNS = (
    "zone_id",
    "hour_sin",
    "hour_cos",
    "weekday",
    "is_weekend",
    "is_peak",
    "distance_scaled",
)
TREATMENT_COLUMNS = ("log_multiplier_x", "log_multiplier_y")
OUTCOME_COLUMNS = ("q_x", "q_y")
COUNT_COLUMNS = ("n_x", "n_y", "n_none")
ORACLE_COLUMNS = {"u", "p_x", "p_y", "p_none", "b_x", "b_y", "theta", "true_probability"}


@dataclasses.dataclass(frozen=True)
class Encoder:
    zones: tuple[int, ...]

    @property
    def names(self) -> list[str]:
        return (
            ["hour_sin", "hour_cos", "is_weekend", "is_peak", "distance_scaled"]
            + [f"zone_{z}" for z in self.zones[1:]]
            + [f"weekday_{d}" for d in range(1, 7)]
        )

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        missing = set(FEATURE_COLUMNS) - set(frame)
        if missing:
            raise ValueError(f"Missing context features: {sorted(missing)}")
        if not frame.zone_id.isin(self.zones).all():
            raise ValueError("Context has a zone outside fixed training taxonomy")
        if not frame.weekday.between(0, 6).all() or not frame.distance_scaled.between(0, 1).all():
            raise ValueError("Context features are outside the declared domain")
        matrix = np.column_stack(
            [
                frame[
                    ["hour_sin", "hour_cos", "is_weekend", "is_peak", "distance_scaled"]
                ].to_numpy(),
                *[(frame.zone_id == z).to_numpy()[:, None] for z in self.zones[1:]],
                *[(frame.weekday == d).to_numpy()[:, None] for d in range(1, 7)],
            ]
        ).astype(float)
        if not np.isfinite(matrix).all():
            raise ValueError("Nonfinite estimator features")
        return matrix


def require_observed(frame: pd.DataFrame) -> None:
    forbidden = ORACLE_COLUMNS.intersection(str(c).lower() for c in frame)
    if forbidden:
        raise ValueError(f"Oracle fields are forbidden in estimation input: {sorted(forbidden)}")
    required = set(FEATURE_COLUMNS + TREATMENT_COLUMNS + OUTCOME_COLUMNS + COUNT_COLUMNS) | {
        "n_sessions",
        "day_id",
        "original_day_id",
        "block_id",
    }
    missing = required - set(frame)
    if missing:
        raise ValueError(f"Missing observed block columns: {sorted(missing)}")
    numeric = frame[[*TREATMENT_COLUMNS, *OUTCOME_COLUMNS, *COUNT_COLUMNS, "n_sessions"]].to_numpy(
        float
    )
    if not np.isfinite(numeric).all() or (frame.n_sessions <= 0).any():
        raise ValueError("Outcomes, treatments and session weights must be finite and valid")
    if (frame[list(OUTCOME_COLUMNS)] < 0).any().any() or (
        frame[list(OUTCOME_COLUMNS)].sum(axis=1) > 1 + 1e-12
    ).any():
        raise ValueError("Invalid observed choice proportions")
    if (frame[list(COUNT_COLUMNS)] < 0).any().any():
        raise ValueError("Choice counts must be non-negative")
    counts_and_sessions = frame[[*COUNT_COLUMNS, "n_sessions"]].to_numpy(float)
    if not np.equal(counts_and_sessions, np.round(counts_and_sessions)).all():
        raise ValueError("Choice counts and n_sessions must be integers")
    if not (frame[list(COUNT_COLUMNS)].sum(axis=1) == frame.n_sessions).all():
        raise ValueError("Choice counts do not conserve sessions")
    for service in ("x", "y"):
        expected = frame[f"n_{service}"] / frame.n_sessions
        if not np.isclose(frame[f"q_{service}"], expected, atol=1e-9, rtol=1e-9).all():
            raise ValueError(
                f"Observed choice proportion q_{service} does not match "
                f"count ratio n_{service} / n_sessions"
            )
    if "q_none" in frame:
        expected_none = frame["n_none"] / frame.n_sessions
        if not np.isclose(frame["q_none"], expected_none, atol=1e-9, rtol=1e-9).all():
            raise ValueError(
                "Observed choice proportion q_none does not match count ratio n_none / n_sessions"
            )


def date_splits(frame: pd.DataFrame, config: Config) -> dict[str, pd.DataFrame]:
    dates = pd.to_datetime(frame.day_id, errors="raise")
    if not ((dates >= config.source.start) & (dates < config.source.end)).all():
        raise ValueError("Block dates are outside the declared scope")
    splits = {
        "train": frame.loc[dates < config.source.train_end].copy(),
        "validation": frame.loc[
            (dates >= config.source.train_end) & (dates < config.source.validation_end)
        ].copy(),
        "test": frame.loc[dates >= config.source.validation_end].copy(),
    }
    if any(part.empty for part in splits.values()):
        raise ValueError("Train, validation and test must each contain blocks")
    day_sets = [set(part.day_id) for part in splits.values()]
    if any(day_sets[i] & day_sets[j] for i in range(3) for j in range(i + 1, 3)):
        raise ValueError("Day leakage across splits")
    return splits


def day_folds(frame: pd.DataFrame, n_splits: int) -> list[tuple[np.ndarray, np.ndarray]]:
    groups = frame.original_day_id.to_numpy()
    if len(np.unique(groups)) < n_splits:
        raise ValueError("Too few original days for the configured cross-fitting folds")
    folds = list(GroupKFold(n_splits=n_splits).split(frame, groups=groups))
    for train, validation in folds:
        if set(groups[train]) & set(groups[validation]):
            raise ValueError("Original day occurs in both sides of a cross-fitting fold")
    return folds
