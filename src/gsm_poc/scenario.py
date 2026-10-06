"""Price scenarios based only on fitted observed models and supported treatments."""

from __future__ import annotations

import dataclasses
from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from gsm_poc.config import Config
from gsm_poc.estimate import ModelBundle
from gsm_poc.generate import PRICE_LEVELS
from gsm_poc.uncertainty import BootstrapResult, percentile_interval
from gsm_poc.validate import valid_probabilities


@dataclasses.dataclass(frozen=True)
class ScenarioRequest:
    scenario_id: str = "price-x-plus10"
    baseline_multiplier_x: float = 1.0
    baseline_multiplier_y: float = 1.0
    delta_price_x: float = 0.10
    delta_price_y: float = 0.0
    n_sessions: int = 10000
    interval_level: float = 0.95
    target_context_set: str = "all"

    def validate(self) -> None:
        values = np.array(
            [
                self.baseline_multiplier_x,
                self.baseline_multiplier_y,
                self.delta_price_x,
                self.delta_price_y,
                self.interval_level,
            ]
        )
        if not np.isfinite(values).all():
            raise ValueError("Scenario parameters must be finite")
        if min(self.baseline_multiplier_x, self.baseline_multiplier_y) <= 0:
            raise ValueError("Baseline price multipliers must be positive")
        if min(self.delta_price_x, self.delta_price_y) <= -1:
            raise ValueError("Price reductions must leave a positive price")
        if type(self.n_sessions) is not int or self.n_sessions <= 0:
            raise ValueError("n_sessions must be a positive integer")
        if not 0 < self.interval_level < 1:
            raise ValueError("interval_level must lie between 0 and 1")
        if not isinstance(self.target_context_set, str) or not self.target_context_set.strip():
            raise ValueError("target_context_set must be a non-empty string")


def _adjacent(value: float) -> list[float]:
    exact = PRICE_LEVELS[np.isclose(PRICE_LEVELS, value, rtol=0, atol=1e-10)]
    if len(exact):
        return [float(exact[0])]
    return [
        float(PRICE_LEVELS[PRICE_LEVELS < value].max()),
        float(PRICE_LEVELS[PRICE_LEVELS > value].min()),
    ]


def joint_support(
    bundle: ModelBundle, contexts: pd.DataFrame, multipliers: np.ndarray, config: Config
) -> tuple[str, list[str]]:
    if (
        not np.isfinite(multipliers).all()
        or (multipliers < 0.9 - 1e-10).any()
        or (multipliers > 1.1 + 1e-10).any()
    ):
        return "out_of_support", ["Price is outside the designed multiplier range 0.90–1.10"]
    reasons = []
    group_columns = ["zone_id", "is_weekend", "is_peak"]
    groups = contexts[group_columns].drop_duplicates()
    for x, y in product(_adjacent(multipliers[0]), _adjacent(multipliers[1])):
        selected = bundle.train_support[
            np.isclose(bundle.train_support.multiplier_x, x)
            & np.isclose(bundle.train_support.multiplier_y, y)
        ]
        if selected.empty:
            return "out_of_support", [f"Joint price corner ({x}, {y}) has no training blocks"]
        counts = selected.groupby(group_columns).size().rename("blocks").reset_index()
        joined = groups.merge(
            counts,
            how="left",
            on=group_columns,
            validate="one_to_one",
        )
        joined["blocks"] = joined.blocks.fillna(0).astype(int)
        for row in joined[joined.blocks < config.model.min_price_cell_count].itertuples(
            index=False
        ):
            reasons.append(
                f"Joint price corner ({x}, {y}) has only {row.blocks} blocks for "
                f"context zone_id={row.zone_id}, is_weekend={row.is_weekend}, "
                f"is_peak={row.is_peak}; minimum {config.model.min_price_cell_count}"
            )
    if (
        bundle.diagnostics.get("condition_number") is None
        or bundle.diagnostics["condition_number"] > config.model.max_condition_number
    ):
        reasons.append("Treatment covariance is poorly conditioned")
    return ("insufficient_support" if reasons else "ok"), reasons


def scenario(
    bundle: ModelBundle | None,
    contexts: pd.DataFrame,
    request: ScenarioRequest,
    config: Config,
    run_id: str,
    draws: BootstrapResult | None = None,
) -> dict:
    request.validate()
    if contexts.empty:
        raise ValueError("No selected scenario context")
    weights = (
        contexts.n_sessions.to_numpy(float) if "n_sessions" in contexts else np.ones(len(contexts))
    )
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("Scenario context session weights must be positive and finite")
    zones = sorted(int(z) for z in contexts.zone_id.unique()) if "zone_id" in contexts else []
    scope = {
        "target_context_set": request.target_context_set,
        "zones": zones,
        "selected_zone": zones[0] if len(zones) == 1 else None,
        "context_blocks": int(len(contexts)),
        "context_weight_sessions": int(weights.sum()),
    }
    output: dict[str, Any] = {
        "run_id": run_id,
        "scenario_id": request.scenario_id,
        "target_context_set": request.target_context_set,
        "scope": scope,
        "source_kind": (
            bundle.source_kind
            if bundle
            else ("semi_synthetic" if config.project.context_mode == "tlc" else "synthetic")
        ),
        "evidence_level": "C",
        "request": dataclasses.asdict(request),
        "units": {
            "probability": "fraction",
            "delta_probability": "percentage_points",
            "bookings": "expected quote-session choices",
            "theta": "probability / log-price",
        },
        "assumption": "Quote session population held fixed; X/Y are hypothetical services",
        "interval": None,
    }
    if bundle is None:
        output.update(status="not_identified", reasons=["A valid model matrix is unavailable"])
        return output
    if bundle.diagnostics.get("validation_probability_valid") is False:
        output.update(
            status="invalid_probability",
            reasons=[
                "Model choice probabilities failed validation; model is ineligible for scenarios"
            ],
        )
        return output
    bundle.encoder.transform(contexts)
    baseline_multiplier = np.array([request.baseline_multiplier_x, request.baseline_multiplier_y])
    target_multiplier = baseline_multiplier * (
        1 + np.array([request.delta_price_x, request.delta_price_y])
    )
    t0, t1 = np.log(baseline_multiplier), np.log(target_multiplier)
    inactive = set(range(2)) - set(bundle.active_treatments)
    for k in inactive:
        observed = bundle.diagnostics["constant_log_prices"][("X", "Y")[k]]
        if abs(t0[k] - observed) > 1e-12 or abs(t1[k] - observed) > 1e-12:
            output.update(
                status="not_identified", reasons=["Scenario changes an unidentified price"]
            )
            return output
    reasons = []
    support_status = "ok"
    for point in (baseline_multiplier, target_multiplier):
        status, point_reasons = joint_support(bundle, contexts, point, config)
        if status == "out_of_support":
            output.update(status=status, reasons=point_reasons)
            return output
        if status == "insufficient_support":
            support_status = status
            reasons.extend(point_reasons)
    before, after = bundle.probabilities(contexts, t0), bundle.probabilities(contexts, t1)
    if not valid_probabilities(before) or not valid_probabilities(after):
        output.update(
            status="invalid_probability",
            reasons=[
                "A context probability is outside the simplex; "
                "no clipping or renormalization applied"
            ],
        )
        return output
    p0, p1 = np.average(before, axis=0, weights=weights), np.average(after, axis=0, weights=weights)
    delta = p1 - p0
    estimates = {
        label: {
            "before_probability": float(p0[j]),
            "after_probability": float(p1[j]),
            "delta_percentage_points": float(delta[j] * 100),
            "before_expected_choices": float(p0[j] * request.n_sessions),
            "after_expected_choices": float(p1[j] * request.n_sessions),
        }
        for j, label in enumerate(("X", "Y", "NONE"))
    }
    total0, total1 = (
        float(p0[:2].sum() * request.n_sessions),
        float(p1[:2].sum() * request.n_sessions),
    )
    theta = [[None, None], [None, None]]
    elasticity = [[None, None], [None, None]]
    for j in range(2):
        for k, active in enumerate(bundle.active_treatments):
            theta[j][active] = float(bundle.theta[j, k])
            if p0[j] >= config.model.elasticity_min_probability:
                elasticity[j][active] = float(bundle.theta[j, k] / p0[j])
    output.update(
        status=support_status,
        support_status=support_status,
        reasons=reasons,
        estimator=bundle.estimator,
        dataset_id=bundle.dataset_id,
        outcome_order=list(bundle.outcome_order),
        treatment_order=list(bundle.treatment_order),
        theta=theta,
        elasticity_at_baseline=elasticity,
        context_blocks=len(contexts),
        context_weight_sessions=int(weights.sum()),
        probabilities=estimates,
        baseline_multiplier=baseline_multiplier.tolist(),
        target_multiplier=target_multiplier.tolist(),
        delta_log_price=(t1 - t0).tolist(),
        before_expected_bookings=total0,
        after_expected_bookings=total1,
        delta_expected_bookings=total1 - total0,
    )
    requested = draws.requested_draws if draws else 0
    failed, invalid, values = 0, 0, []
    theta_values, elasticity_values = [], []
    if draws:
        for draw in draws.bundles:
            if draw is None:
                failed += 1
                continue
            b, a = draw.probabilities(contexts, t0), draw.probabilities(contexts, t1)
            if not valid_probabilities(b) or not valid_probabilities(a):
                invalid += 1
                continue
            avg0, avg1 = (
                np.average(b, axis=0, weights=weights),
                np.average(a, axis=0, weights=weights),
            )
            theta_values.append(draw.theta)
            # Small baseline probabilities disable elasticity intervals separately.
            elasticity_values.append(
                np.divide(
                    draw.theta,
                    avg0[:2, None],
                    out=np.full_like(draw.theta, np.nan),
                    where=avg0[:2, None] >= config.model.elasticity_min_probability,
                )
            )
            values.append(
                np.concatenate(
                    [
                        avg0,
                        avg1,
                        (avg1 - avg0) * 100,
                        [(avg1[:2].sum() - avg0[:2].sum()) * request.n_sessions],
                    ]
                )
            )
    failure_fraction = (failed + invalid) / requested if requested else 1.0
    stable = (
        draws is not None
        and draws.interval_status == "ok"
        and len(values) >= config.evaluation.reporting_min_draws
        and failure_fraction <= config.evaluation.max_failure_fraction
    )
    output["bootstrap"] = {
        "requested_draws": requested,
        "fit_failed_draws": failed,
        "invalid_probability_draws": invalid,
        "valid_draws": len(values),
        "failure_fraction": failure_fraction,
        "interval_status": "ok" if stable else "interval_unstable",
    }
    if stable:
        # Do not condition intervals on dropping invalid draws: any invalid probability
        # suppresses an interval, even if the failure rate is below the warning limit.
        if invalid:
            stable = False
            output["bootstrap"]["interval_status"] = "interval_unstable"
        else:
            low, high = percentile_interval(np.array(values), request.interval_level)
            names = [
                f"{label}_{metric}"
                for metric in ("before_probability", "after_probability", "delta_percentage_points")
                for label in ("X", "Y", "NONE")
            ] + ["delta_expected_bookings"]
            output["interval"] = {
                name: {"lower": float(low[i]), "upper": float(high[i])}
                for i, name in enumerate(names)
            }
            output["interval_level"] = request.interval_level
            theta_low, theta_high = percentile_interval(
                np.array(theta_values), request.interval_level
            )
            output["theta_interval"] = [[None, None], [None, None]]
            output["elasticity_interval"] = [[None, None], [None, None]]
            elasticities = np.array(elasticity_values)
            for j in range(2):
                for k, active in enumerate(bundle.active_treatments):
                    output["theta_interval"][j][active] = {
                        "lower": float(theta_low[j, k]),
                        "upper": float(theta_high[j, k]),
                    }
                    if np.isfinite(elasticities[:, j, k]).all():
                        low_el, high_el = percentile_interval(
                            elasticities[:, j, k], request.interval_level
                        )
                        output["elasticity_interval"][j][active] = {
                            "lower": float(low_el),
                            "upper": float(high_el),
                        }
    if not stable and output["status"] == "ok":
        output["status"] = "interval_unstable"
        output["reasons"].append("Bootstrap interval is unavailable or requires a reporting run")
    return output
