"""Observed-only price subspaces and rank-one joint-price support."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from gsm_poc.causal.estimate import ModelBundle
    from gsm_poc.core.config import Config

RANK_ATOL = 1e-10
SPAN_ATOL = 1e-8


def price_basis(residual: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, float | None]:
    _, singular, right = np.linalg.svd(
        residual * np.sqrt(weights / weights.sum())[:, None], full_matrices=False
    )
    retained = singular**2 > RANK_ATOL
    basis = right[retained].T
    if basis.shape[1] == residual.shape[1]:
        basis = np.eye(residual.shape[1])
    condition = (
        float((singular[retained].max() / singular[retained].min()) ** 2)
        if retained.any()
        else None
    )
    return basis, condition


def identifies(bundle: ModelBundle, contrast: np.ndarray) -> bool:
    contrast = np.asarray(contrast, dtype=float)
    if contrast.shape != (2,) or not np.isfinite(contrast).all():
        raise ValueError("Price contrast must have two finite log-price components")
    inactive = list(set(range(2)) - set(bundle.active_treatments))
    if inactive and np.max(np.abs(contrast[inactive])) > SPAN_ATOL:
        return False
    basis = getattr(bundle, "contrast_basis", None)
    if basis is None:
        return True
    active = contrast[list(bundle.active_treatments)]
    return bool(np.max(np.abs(active - active @ basis @ basis.T)) <= SPAN_ATOL)


def price_levels_identified(
    bundle: ModelBundle, contexts: pd.DataFrame, treatment: np.ndarray
) -> bool:
    basis = getattr(bundle, "contrast_basis", None)
    if basis is None:
        return True
    treatment = np.broadcast_to(np.asarray(treatment, dtype=float), (len(contexts), 2))
    if not np.isfinite(treatment).all():
        raise ValueError("Nonfinite log-price levels")
    for k in set(range(2)) - set(bundle.active_treatments):
        if (
            np.max(
                np.abs(treatment[:, k] - bundle.diagnostics["constant_log_prices"][("X", "Y")[k]])
            )
            > SPAN_ATOL
        ):
            return False
    price_model = bundle.price_context_model
    if price_model is None:
        raise ValueError("Contrast model lacks its price/context anchor")
    anchor = price_model.predict(bundle.encoder.transform(contexts))
    residual = treatment[:, bundle.active_treatments] - anchor
    return bool(np.max(np.abs(residual - residual @ basis @ basis.T)) <= SPAN_ATOL)


def line_support(
    bundle: ModelBundle, contexts: pd.DataFrame, multipliers: np.ndarray, config: Config
) -> tuple[str, list[str]]:
    """Require actual bracketing joint points in each requested context group."""
    groups = ["zone_id", "is_weekend", "is_peak"]
    points = bundle.train_support[["multiplier_x", "multiplier_y"]].drop_duplicates().to_numpy()
    logs = np.log(points)
    direction = logs[-1] - logs[0]
    length = np.linalg.norm(direction)
    if length <= SPAN_ATOL:
        return "insufficient_support", ["No joint price line in training support"]
    direction /= length
    coordinates = (logs - logs[0]) @ direction
    perpendicular = logs - logs[0] - coordinates[:, None] * direction
    if np.max(np.abs(perpendicular)) > SPAN_ATOL:
        return "insufficient_support", ["Rank-one support requires one observed affine price line"]
    requested = np.log(multipliers) - logs[0]
    coordinate = float(requested @ direction)
    if np.max(np.abs(requested - coordinate * direction)) > SPAN_ATOL:
        return "out_of_support", ["Price levels are outside the observed joint price line"]
    exact = np.flatnonzero(np.isclose(coordinates, coordinate, atol=SPAN_ATOL, rtol=0))
    if len(exact):
        indices = [int(exact[0])]
    else:
        lower, upper = (
            np.flatnonzero(coordinates < coordinate),
            np.flatnonzero(coordinates > coordinate),
        )
        if not len(lower) or not len(upper):
            return "out_of_support", ["Price levels lack bracketing joint training points"]
        indices = [
            int(lower[np.argmax(coordinates[lower])]),
            int(upper[np.argmin(coordinates[upper])]),
        ]
    reasons = []
    for index in indices:
        point = points[index]
        selected = bundle.train_support[
            np.isclose(bundle.train_support.multiplier_x, point[0])
            & np.isclose(bundle.train_support.multiplier_y, point[1])
        ]
        counts = selected.groupby(groups).size()
        for group in contexts[groups].drop_duplicates().itertuples(index=False, name=None):
            count = int(counts.get(group, 0))
            if count < config.model.min_price_cell_count:
                reasons.append(
                    f"Joint point {point.tolist()} has {count} blocks for {group}; "
                    f"minimum {config.model.min_price_cell_count}"
                )
    return ("insufficient_support" if reasons else "ok"), reasons
