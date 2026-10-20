"""Price scenarios based only on fitted observed models and supported treatments."""

from __future__ import annotations

import dataclasses
from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from gsm_poc.causal.analytic import analytic_intervals
from gsm_poc.causal.estimate import ModelBundle
from gsm_poc.causal.features import PRICE_LEVELS
from gsm_poc.causal.forecast_contract import make_metric_record, select_scenario_contexts
from gsm_poc.causal.identification import identifies, line_support, price_levels_identified
from gsm_poc.causal.uncertainty import BootstrapResult, percentile_interval
from gsm_poc.core.config import Config
from gsm_poc.core.validators import valid_probabilities


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
    horizon_start: str | None = None
    horizon_end: str | None = None

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
        if (self.horizon_start is None) != (self.horizon_end is None):
            raise ValueError("horizon_start and horizon_end must both be provided or both omitted")
        if self.horizon_start is not None and self.horizon_end is not None:
            if not isinstance(self.horizon_start, str) or not self.horizon_start.strip():
                raise ValueError("horizon_start must be an ISO timestamp string with offset")
            if not isinstance(self.horizon_end, str) or not self.horizon_end.strip():
                raise ValueError("horizon_end must be an ISO timestamp string with offset")
            try:
                start_ts = pd.Timestamp(self.horizon_start)
                end_ts = pd.Timestamp(self.horizon_end)
            except Exception as exc:
                raise ValueError(f"Invalid horizon timestamp format: {exc}") from exc
            if pd.isna(start_ts) or start_ts.tzinfo is None:
                raise ValueError("horizon_start must be an ISO timestamp with an explicit offset")
            if pd.isna(end_ts) or end_ts.tzinfo is None:
                raise ValueError("horizon_end must be an ISO timestamp with an explicit offset")
            if end_ts <= start_ts:
                raise ValueError("horizon_end must be strictly after horizon_start")


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
    basis = getattr(bundle, "contrast_basis", None)
    if basis is not None and basis.shape[1] < len(bundle.active_treatments):
        if (
            bundle.diagnostics.get("condition_number") is None
            or bundle.diagnostics["condition_number"] > config.model.max_condition_number
        ):
            return "insufficient_support", ["Retained treatment covariance is poorly conditioned"]
        return line_support(bundle, contexts, multipliers, config)
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


def _build_empty_metrics(
    status: str,
    id_status: str,
    sup_status: str,
    reasons: list[str],
) -> dict[str, Any]:
    metrics = {}
    for label in ("X", "Y", "NONE"):
        key = label.lower()
        metrics[f"probability_baseline_{key}"] = make_metric_record(
            metric_id=f"probability_baseline_{key}",
            service=label,
            period="baseline",
            estimate=None,
            unit="fraction",
            status=status,
            identification_status=id_status,
            support_status=sup_status,
            interval_status="interval_unavailable",
            interval=None,
            reasons=reasons,
        )
        metrics[f"probability_target_{key}"] = make_metric_record(
            metric_id=f"probability_target_{key}",
            service=label,
            period="target",
            estimate=None,
            unit="fraction",
            status=status,
            identification_status=id_status,
            support_status=sup_status,
            interval_status="interval_unavailable",
            interval=None,
            reasons=reasons,
        )
        metrics[f"probability_delta_{key}"] = make_metric_record(
            metric_id=f"probability_delta_{key}",
            service=label,
            period="delta",
            estimate=None,
            unit="percentage_points",
            status=status,
            identification_status=id_status,
            support_status=sup_status,
            interval_status="interval_unavailable",
            interval=None,
            reasons=reasons,
        )
        if label != "NONE":
            metrics[f"expected_requests_baseline_{key}"] = make_metric_record(
                metric_id=f"expected_requests_baseline_{key}",
                service=label,
                period="baseline",
                estimate=None,
                unit="requests",
                status=status,
                identification_status=id_status,
                support_status=sup_status,
                interval_status="interval_unavailable",
                interval=None,
                reasons=reasons,
            )
            metrics[f"expected_requests_target_{key}"] = make_metric_record(
                metric_id=f"expected_requests_target_{key}",
                service=label,
                period="target",
                estimate=None,
                unit="requests",
                status=status,
                identification_status=id_status,
                support_status=sup_status,
                interval_status="interval_unavailable",
                interval=None,
                reasons=reasons,
            )
            metrics[f"expected_requests_delta_{key}"] = make_metric_record(
                metric_id=f"expected_requests_delta_{key}",
                service=label,
                period="delta",
                estimate=None,
                unit="requests",
                status=status,
                identification_status=id_status,
                support_status=sup_status,
                interval_status="interval_unavailable",
                interval=None,
                reasons=reasons,
            )
        else:
            metrics["expected_non_booking_sessions_baseline"] = make_metric_record(
                metric_id="expected_non_booking_sessions_baseline",
                service="NONE",
                period="baseline",
                estimate=None,
                unit="non_booking_sessions",
                status=status,
                identification_status=id_status,
                support_status=sup_status,
                interval_status="interval_unavailable",
                interval=None,
                reasons=reasons,
            )
            metrics["expected_non_booking_sessions_target"] = make_metric_record(
                metric_id="expected_non_booking_sessions_target",
                service="NONE",
                period="target",
                estimate=None,
                unit="non_booking_sessions",
                status=status,
                identification_status=id_status,
                support_status=sup_status,
                interval_status="interval_unavailable",
                interval=None,
                reasons=reasons,
            )
            metrics["expected_non_booking_sessions_delta"] = make_metric_record(
                metric_id="expected_non_booking_sessions_delta",
                service="NONE",
                period="delta",
                estimate=None,
                unit="non_booking_sessions",
                status=status,
                identification_status=id_status,
                support_status=sup_status,
                interval_status="interval_unavailable",
                interval=None,
                reasons=reasons,
            )
    for period in ("baseline", "target", "delta"):
        metrics[f"expected_requests_{period}_total"] = make_metric_record(
            metric_id=f"expected_requests_{period}_total",
            service="TOTAL",
            period=period,
            estimate=None,
            unit="requests",
            status=status,
            identification_status=id_status,
            support_status=sup_status,
            interval_status="interval_unavailable",
            interval=None,
            reasons=reasons,
        )
    return metrics


def scenario(
    bundle: ModelBundle | None,
    contexts: pd.DataFrame,
    request: ScenarioRequest,
    config: Config,
    run_id: str,
    draws: BootstrapResult | None = None,
    *,
    inference_method: str = "analytic",
    provenance: dict[str, Any] | None = None,
    selected_scope: dict[str, Any] | None = None,
) -> dict:
    if inference_method not in ("analytic", "bootstrap"):
        raise ValueError("inference_method must be analytic or bootstrap")
    request.validate()
    if contexts.empty:
        raise ValueError("No selected scenario context")

    if selected_scope is not None:
        selected_contexts = contexts
        scope_info = selected_scope
    else:
        tz_name = getattr(config.source, "assumed_timezone", "America/New_York")
        slot_mins = getattr(config.simulation, "slot_minutes", 60)
        selected_contexts, scope_info = select_scenario_contexts(
            contexts,
            target_context_set=request.target_context_set,
            horizon_start=request.horizon_start,
            horizon_end=request.horizon_end,
            timezone=tz_name,
            slot_minutes=slot_mins,
        )

    weights = (
        selected_contexts.n_sessions.to_numpy(float)
        if "n_sessions" in selected_contexts
        else np.ones(len(selected_contexts))
    )
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("Scenario context session weights must be positive and finite")

    scope = {
        "target_context_set": request.target_context_set,
        "zones": scope_info.get("zones", []),
        "selected_zone": scope_info.get("selected_zone"),
        "services": ["X", "Y"],
        "timezone": scope_info.get("timezone", "unavailable"),
        "horizon_start": scope_info.get("horizon_start", "unavailable"),
        "horizon_end": scope_info.get("horizon_end", "unavailable"),
        "context_blocks": int(len(selected_contexts)),
        "context_weight_sessions": int(weights.sum()),
        "fixed_quote_population": int(request.n_sessions),
    }

    prov = {
        "run_id": provenance.get("run_id", "unavailable") if provenance else "unavailable",
        "model_run_id": (
            provenance.get("model_run_id", "unavailable") if provenance else "unavailable"
        ),
        "estimator": bundle.estimator if bundle else "unavailable",
        "dataset_id": (
            getattr(bundle, "dataset_id", None)
            or (provenance.get("dataset_id") if provenance else None)
            or "unavailable"
        ),
        "source_context_sha256": (
            provenance.get("source_context_sha256", "unavailable") if provenance else "unavailable"
        ),
        "selected_blocks_sha256": scope_info.get("selected_blocks_sha256", "unavailable"),
        "source_config_hash": (
            provenance.get("source_config_hash", "unavailable") if provenance else "unavailable"
        ),
        "code_version": (
            provenance.get("code_version", "unavailable") if provenance else "unavailable"
        ),
        "rules_version": "forecast_contract_v2",
    }

    evidence = {
        "source_kind": (
            bundle.source_kind
            if bundle
            else ("semi_synthetic" if config.project.context_mode == "tlc" else "synthetic")
        ),
        "evidence_level": "C",
        "inference_method": inference_method,
        "interval_kind": (
            "analytic score/delta method; individual intervals"
            if inference_method == "analytic"
            else "day-bootstrap percentile; individual intervals"
        ),
        "interval_scope": "individual",
        "interval_validation_scope": "technical_checks_only",
        "interval_calibration_status": "not_evaluated_for_this_run",
        "calibration_status": "not_evaluated_for_this_run",
        "notes": (
            "Technical numerical checks only; "
            "operational coverage has not been evaluated for this run."
        ),
    }

    output: dict[str, Any] = {
        "schema_version": 2,
        "run_id": run_id,
        "scenario_id": request.scenario_id,
        "target_context_set": request.target_context_set,
        "scope": scope,
        "provenance": prov,
        "evidence": evidence,
        "source_kind": evidence["source_kind"],
        "evidence_level": evidence["evidence_level"],
        "request": dataclasses.asdict(request),
        "units": {
            "probability": "fraction",
            "delta_probability": "percentage_points",
            "bookings": "expected quote-session choices",
            "theta": "probability / log-price",
        },
        "assumption": "Quote session population held fixed; X/Y are hypothetical services",
        "inference_method": inference_method,
        "interval_kind": evidence["interval_kind"],
        "interval_scope": evidence["interval_scope"],
        "interval_validation_scope": evidence["interval_validation_scope"],
        "interval_calibration_status": evidence["interval_calibration_status"],
        "coverage_warning": (
            "Technical stability does not certify nominal coverage; "
            "calibration has not been evaluated for this run."
        ),
        "interval_level": float(request.interval_level),
        "interval": None,
    }

    if bundle is None:
        reasons = ["A valid model matrix is unavailable"]
        output.update(
            status="not_identified",
            reasons=reasons,
            identification={
                "status": "not_identified",
                "baseline_identified": False,
                "target_identified": False,
                "contrast_identified": False,
                "absolute_levels_identified": False,
                "reasons": reasons,
            },
            support={"status": "not_evaluated", "reasons": []},
            metrics=_build_empty_metrics(
                "not_identified", "not_identified", "not_evaluated", reasons
            ),
        )
        return output

    if bundle.diagnostics.get("validation_probability_valid") is False:
        reasons = [
            "Model choice probabilities failed validation; model is ineligible for scenarios"
        ]
        output.update(
            status="invalid_probability",
            reasons=reasons,
            identification={
                "status": "not_evaluated",
                "baseline_identified": False,
                "target_identified": False,
                "contrast_identified": False,
                "absolute_levels_identified": False,
                "reasons": [],
            },
            support={"status": "not_evaluated", "reasons": []},
            metrics=_build_empty_metrics(
                "invalid_probability", "not_evaluated", "not_evaluated", reasons
            ),
        )
        return output

    bundle.encoder.transform(selected_contexts)
    baseline_multiplier = np.array(
        [request.baseline_multiplier_x, request.baseline_multiplier_y], dtype=float
    )
    target_multiplier = baseline_multiplier * (
        1.0 + np.array([request.delta_price_x, request.delta_price_y], dtype=float)
    )
    t0, t1 = np.log(baseline_multiplier), np.log(target_multiplier)

    if getattr(bundle, "contrast_basis", None) is not None:
        identified = identifies(bundle, t1 - t0)
        levels = all(
            price_levels_identified(bundle, selected_contexts, point) for point in (t0, t1)
        )
        output["identification"] = {
            "status": "ok" if identified and levels else "not_identified",
            "contrast_identified": identified,
            "absolute_levels_identified": levels,
            "residual_rank": bundle.diagnostics["residual_rank"],
            "rule_version": "contrast_subspace_v1",
            "delta_log_price": (t1 - t0).tolist(),
            "causal_assumption": bundle.diagnostics["causal_assumption"],
        }
        if not identified or not levels:
            reasons = ["Requested contrast or absolute price levels lack identification"]
            output.update(
                status="not_identified",
                reasons=reasons,
                support={"status": "not_evaluated", "reasons": []},
                metrics=_build_empty_metrics(
                    "not_identified", "not_identified", "not_evaluated", reasons
                ),
            )
            return output
    else:
        output["identification"] = {
            "status": "ok",
            "contrast_identified": True,
            "absolute_levels_identified": True,
            "residual_rank": bundle.diagnostics.get("residual_rank", 2),
            "rule_version": "full_rank_v1",
            "delta_log_price": (t1 - t0).tolist(),
            "causal_assumption": bundle.diagnostics.get("causal_assumption"),
        }

    inactive = set(range(2)) - set(bundle.active_treatments)
    for k in inactive:
        observed = bundle.diagnostics["constant_log_prices"][("X", "Y")[k]]
        if abs(t0[k] - observed) > 1e-12 or abs(t1[k] - observed) > 1e-12:
            reasons = ["Scenario changes an unidentified price"]
            output["identification"]["status"] = "not_identified"
            output["identification"]["contrast_identified"] = False
            output["identification"]["absolute_levels_identified"] = False
            output.update(
                status="not_identified",
                reasons=reasons,
                support={"status": "not_evaluated", "reasons": []},
                metrics=_build_empty_metrics(
                    "not_identified", "not_identified", "not_evaluated", reasons
                ),
            )
            return output

    b_support, b_sup_reasons = joint_support(bundle, selected_contexts, baseline_multiplier, config)
    t_support, t_sup_reasons = joint_support(bundle, selected_contexts, target_multiplier, config)

    support_status = "ok"
    reasons = []
    output["support"] = {
        "status": "ok",
        "baseline_status": b_support,
        "baseline_reasons": b_sup_reasons,
        "target_status": t_support,
        "target_reasons": t_sup_reasons,
        "thresholds": {
            "min_price_cell_count": config.model.min_price_cell_count,
            "max_condition_number": config.model.max_condition_number,
        },
        "reasons": [],
    }

    for pt_status, pt_reasons in [(b_support, b_sup_reasons), (t_support, t_sup_reasons)]:
        if pt_status == "out_of_support":
            output["support"]["status"] = "out_of_support"
            output["support"]["reasons"] = pt_reasons
            output.update(
                status="out_of_support",
                support_status="out_of_support",
                reasons=pt_reasons,
                metrics=_build_empty_metrics("out_of_support", "ok", "out_of_support", pt_reasons),
            )
            return output
        if pt_status == "insufficient_support":
            support_status = pt_status
            reasons.extend(pt_reasons)

    output["support"]["status"] = support_status
    output["support"]["reasons"] = reasons

    b_ok = b_support == "ok"
    t_ok = t_support == "ok"
    delta_ok = b_ok and t_ok

    if getattr(bundle, "contrast_basis", None) is not None and support_status != "ok":
        output.update(
            status=support_status,
            support_status=support_status,
            reasons=reasons,
            metrics=_build_empty_metrics(support_status, "ok", support_status, reasons),
        )
        return output

    if not b_ok and not t_ok:
        output.update(
            status=support_status,
            support_status=support_status,
            reasons=reasons,
            metrics=_build_empty_metrics(support_status, "ok", support_status, reasons),
        )
        return output

    raw_before = bundle.probabilities(selected_contexts, t0)
    raw_after = bundle.probabilities(selected_contexts, t1)

    if not valid_probabilities(raw_before) or not valid_probabilities(raw_after):
        inv_reasons = [
            "A context probability is outside the simplex; no clipping or renormalization applied"
        ]
        output.update(
            status="invalid_probability",
            reasons=inv_reasons,
            metrics=_build_empty_metrics("invalid_probability", "ok", support_status, inv_reasons),
        )
        return output

    raw_p0 = np.average(raw_before, axis=0, weights=weights)
    raw_p1 = np.average(raw_after, axis=0, weights=weights)
    raw_delta = raw_p1 - raw_p0
    raw_total0 = float(raw_p0[:2].sum() * request.n_sessions)
    raw_total1 = float(raw_p1[:2].sum() * request.n_sessions)
    raw_delta_total = raw_total1 - raw_total0

    p0 = raw_p0 if b_ok else None
    p1 = raw_p1 if t_ok else None
    delta = raw_delta if delta_ok else None
    total0 = raw_total0 if b_ok else None
    total1 = raw_total1 if t_ok else None
    delta_total = raw_delta_total if delta_ok else None

    theta = [[None, None], [None, None]]
    elasticity = [[None, None], [None, None]]
    for j in range(2):
        for k, active in enumerate(bundle.active_treatments):
            if not identifies(bundle, np.eye(2)[active]):
                continue
            theta[j][active] = float(bundle.theta[j, k])
            if raw_p0[j] >= config.model.elasticity_min_probability:
                elasticity[j][active] = float(bundle.theta[j, k] / raw_p0[j])

    interval_dict: dict[str, dict[str, float]] = {}
    theta_intervals = [[None, None], [None, None]]
    elasticity_intervals = [[None, None], [None, None]]
    interval_status = "interval_unavailable"
    inference_reasons = []

    if inference_method == "analytic":
        analytic_res = analytic_intervals(
            bundle,
            selected_contexts,
            weights,
            t0,
            t1,
            {
                "probabilities": {
                    label: {
                        "before_probability": float(raw_p0[j]),
                        "after_probability": float(raw_p1[j]),
                        "delta_percentage_points": float(raw_delta[j] * 100),
                        "before_expected_choices": float(raw_p0[j] * request.n_sessions),
                        "after_expected_choices": float(raw_p1[j] * request.n_sessions),
                    }
                    for j, label in enumerate(("X", "Y", "NONE"))
                },
                "before_expected_bookings": raw_total0,
                "after_expected_bookings": raw_total1,
                "delta_expected_bookings": raw_delta_total,
                "elasticity_at_baseline": elasticity,
            },
            request.interval_level,
            request.n_sessions,
        )
        output["analytic"] = analytic_res.get("analytic", {})
        interval_status = output["analytic"].get("interval_status", "interval_unavailable")
        if interval_status == "ok":
            interval_dict = analytic_res.get("interval", {})
            theta_intervals = analytic_res.get("theta_interval", theta_intervals)
            elasticity_intervals = analytic_res.get("elasticity_interval", elasticity_intervals)
        else:
            if "reason" in output["analytic"]:
                inference_reasons.append(output["analytic"]["reason"])
    else:
        requested = draws.requested_draws if draws else 0
        failed, invalid, lost_id, values = 0, 0, 0, []
        th_vals, el_vals = [], []
        if draws:
            for draw in draws.bundles:
                if draw is None:
                    failed += 1
                    continue
                if getattr(bundle, "contrast_basis", None) is not None and (
                    not identifies(draw, t1 - t0)
                    or not all(
                        price_levels_identified(draw, selected_contexts, pt) for pt in (t0, t1)
                    )
                ):
                    lost_id += 1
                    continue
                b = draw.probabilities(selected_contexts, t0)
                a = draw.probabilities(selected_contexts, t1)
                if not valid_probabilities(b) or not valid_probabilities(a):
                    invalid += 1
                    continue
                avg0 = np.average(b, axis=0, weights=weights)
                avg1 = np.average(a, axis=0, weights=weights)
                th_vals.append(draw.theta)
                el_vals.append(
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
                            [avg0[:2].sum() * request.n_sessions],
                            [avg1[:2].sum() * request.n_sessions],
                            avg0 * request.n_sessions,
                            avg1 * request.n_sessions,
                            (avg1 - avg0) * request.n_sessions,
                        ]
                    )
                )
        failure_fraction = (failed + invalid + lost_id) / requested if requested else 1.0
        stable = (
            draws is not None
            and draws.interval_status == "ok"
            and not invalid
            and len(values) >= config.evaluation.reporting_min_draws
            and failure_fraction <= config.evaluation.max_failure_fraction
        )
        if getattr(bundle, "contrast_basis", None) is not None and (failed or lost_id):
            stable = False
        output["bootstrap"] = {
            "requested_draws": requested,
            "fit_failed_draws": failed,
            "invalid_probability_draws": invalid,
            "valid_draws": len(values),
            "failure_fraction": failure_fraction,
            "interval_status": "ok" if stable else "interval_unstable",
            **(
                {"lost_identification_draws": lost_id}
                if getattr(bundle, "contrast_basis", None) is not None
                else {}
            ),
        }
        if stable:
            low, high = percentile_interval(np.array(values), request.interval_level)
            metric_names = [
                f"{label}_{metric}"
                for metric in ("before_probability", "after_probability", "delta_percentage_points")
                for label in ("X", "Y", "NONE")
            ] + [
                "delta_expected_bookings",
                "before_expected_bookings",
                "after_expected_bookings",
                "X_before_expected_choices",
                "Y_before_expected_choices",
                "NONE_before_expected_choices",
                "X_after_expected_choices",
                "Y_after_expected_choices",
                "NONE_after_expected_choices",
                "X_delta_expected_choices",
                "Y_delta_expected_choices",
                "NONE_delta_expected_choices",
            ]
            interval_dict = {
                name: {"lower": float(low[i]), "upper": float(high[i])}
                for i, name in enumerate(metric_names)
            }
            interval_status = "ok"
            th_low, th_high = percentile_interval(np.array(th_vals), request.interval_level)
            elasticities = np.array(el_vals)
            for j in range(2):
                for k, active in enumerate(bundle.active_treatments):
                    if not identifies(bundle, np.eye(2)[active]) or any(
                        not identifies(draw, np.eye(2)[active])
                        for draw in draws.bundles  # type: ignore[union-attr]
                        if draw is not None
                    ):
                        continue
                    theta_intervals[j][active] = {
                        "lower": float(th_low[j, k]),
                        "upper": float(th_high[j, k]),
                    }
                    if np.isfinite(elasticities[:, j, k]).all():
                        low_el, high_el = percentile_interval(
                            elasticities[:, j, k], request.interval_level
                        )
                        elasticity_intervals[j][active] = {
                            "lower": float(low_el),
                            "upper": float(high_el),
                        }
        else:
            interval_status = "interval_unstable"
            inference_reasons.append(
                "Bootstrap interval is unavailable or requires a reporting run"
            )

    delta_ok = b_ok and t_ok

    metrics = {}
    for j, label in enumerate(("X", "Y", "NONE")):
        key = label.lower()
        p0_val = float(p0[j]) if (b_ok and p0 is not None) else None
        p1_val = float(p1[j]) if (t_ok and p1 is not None) else None
        d_val = float(delta[j] * 100) if (delta_ok and delta is not None) else None
        exp0 = float(p0[j] * request.n_sessions) if (b_ok and p0 is not None) else None
        exp1 = float(p1[j] * request.n_sessions) if (t_ok and p1 is not None) else None
        d_exp = (exp1 - exp0) if (exp1 is not None and exp0 is not None) else None

        metrics[f"probability_baseline_{key}"] = make_metric_record(
            metric_id=f"probability_baseline_{key}",
            service=label,
            period="baseline",
            estimate=p0_val,
            unit="fraction",
            status="ok" if b_ok else b_support,
            identification_status="ok",
            support_status=b_support,
            interval_status=interval_status if b_ok else "interval_unavailable",
            interval=interval_dict.get(f"{label}_before_probability") if b_ok else None,
            reasons=[] if b_ok else b_sup_reasons,
        )
        metrics[f"probability_target_{key}"] = make_metric_record(
            metric_id=f"probability_target_{key}",
            service=label,
            period="target",
            estimate=p1_val,
            unit="fraction",
            status="ok" if t_ok else t_support,
            identification_status="ok",
            support_status=t_support,
            interval_status=interval_status if t_ok else "interval_unavailable",
            interval=interval_dict.get(f"{label}_after_probability") if t_ok else None,
            reasons=[] if t_ok else t_sup_reasons,
        )
        metrics[f"probability_delta_{key}"] = make_metric_record(
            metric_id=f"probability_delta_{key}",
            service=label,
            period="delta",
            estimate=d_val,
            unit="percentage_points",
            status="ok" if delta_ok else (t_support if not t_ok else b_support),
            identification_status="ok",
            support_status="ok" if delta_ok else (t_support if not t_ok else b_support),
            interval_status=interval_status if delta_ok else "interval_unavailable",
            interval=interval_dict.get(f"{label}_delta_percentage_points") if delta_ok else None,
            reasons=[] if delta_ok else (b_sup_reasons + t_sup_reasons),
        )
        if label != "NONE":
            metrics[f"expected_requests_baseline_{key}"] = make_metric_record(
                metric_id=f"expected_requests_baseline_{key}",
                service=label,
                period="baseline",
                estimate=exp0,
                unit="requests",
                status="ok" if b_ok else b_support,
                identification_status="ok",
                support_status=b_support,
                interval_status=interval_status if b_ok else "interval_unavailable",
                interval=interval_dict.get(f"{label}_before_expected_choices") if b_ok else None,
                reasons=[] if b_ok else b_sup_reasons,
            )
            metrics[f"expected_requests_target_{key}"] = make_metric_record(
                metric_id=f"expected_requests_target_{key}",
                service=label,
                period="target",
                estimate=exp1,
                unit="requests",
                status="ok" if t_ok else t_support,
                identification_status="ok",
                support_status=t_support,
                interval_status=interval_status if t_ok else "interval_unavailable",
                interval=interval_dict.get(f"{label}_after_expected_choices") if t_ok else None,
                reasons=[] if t_ok else t_sup_reasons,
            )
            metrics[f"expected_requests_delta_{key}"] = make_metric_record(
                metric_id=f"expected_requests_delta_{key}",
                service=label,
                period="delta",
                estimate=d_exp,
                unit="requests",
                status="ok" if delta_ok else (t_support if not t_ok else b_support),
                identification_status="ok",
                support_status="ok" if delta_ok else (t_support if not t_ok else b_support),
                interval_status=interval_status if delta_ok else "interval_unavailable",
                interval=interval_dict.get(f"{label}_delta_expected_choices") if delta_ok else None,
                reasons=[] if delta_ok else (b_sup_reasons + t_sup_reasons),
            )
        else:
            metrics["expected_non_booking_sessions_baseline"] = make_metric_record(
                metric_id="expected_non_booking_sessions_baseline",
                service="NONE",
                period="baseline",
                estimate=exp0,
                unit="non_booking_sessions",
                status="ok" if b_ok else b_support,
                identification_status="ok",
                support_status=b_support,
                interval_status=interval_status if b_ok else "interval_unavailable",
                interval=interval_dict.get("NONE_before_expected_choices") if b_ok else None,
                reasons=[] if b_ok else b_sup_reasons,
            )
            metrics["expected_non_booking_sessions_target"] = make_metric_record(
                metric_id="expected_non_booking_sessions_target",
                service="NONE",
                period="target",
                estimate=exp1,
                unit="non_booking_sessions",
                status="ok" if t_ok else t_support,
                identification_status="ok",
                support_status=t_support,
                interval_status=interval_status if t_ok else "interval_unavailable",
                interval=interval_dict.get("NONE_after_expected_choices") if t_ok else None,
                reasons=[] if t_ok else t_sup_reasons,
            )
            metrics["expected_non_booking_sessions_delta"] = make_metric_record(
                metric_id="expected_non_booking_sessions_delta",
                service="NONE",
                period="delta",
                estimate=d_exp,
                unit="non_booking_sessions",
                status="ok" if delta_ok else (t_support if not t_ok else b_support),
                identification_status="ok",
                support_status="ok" if delta_ok else (t_support if not t_ok else b_support),
                interval_status=interval_status if delta_ok else "interval_unavailable",
                interval=interval_dict.get("NONE_delta_expected_choices") if delta_ok else None,
                reasons=[] if delta_ok else (b_sup_reasons + t_sup_reasons),
            )

    metrics["expected_requests_baseline_total"] = make_metric_record(
        metric_id="expected_requests_baseline_total",
        service="TOTAL",
        period="baseline",
        estimate=total0 if (b_ok and total0 is not None) else None,
        unit="requests",
        status="ok" if b_ok else b_support,
        identification_status="ok",
        support_status=b_support,
        interval_status=interval_status if b_ok else "interval_unavailable",
        interval=interval_dict.get("before_expected_bookings") if b_ok else None,
        reasons=[] if b_ok else b_sup_reasons,
    )
    metrics["expected_requests_target_total"] = make_metric_record(
        metric_id="expected_requests_target_total",
        service="TOTAL",
        period="target",
        estimate=total1 if (t_ok and total1 is not None) else None,
        unit="requests",
        status="ok" if t_ok else t_support,
        identification_status="ok",
        support_status=t_support,
        interval_status=interval_status if t_ok else "interval_unavailable",
        interval=interval_dict.get("after_expected_bookings") if t_ok else None,
        reasons=[] if t_ok else t_sup_reasons,
    )
    metrics["expected_requests_delta_total"] = make_metric_record(
        metric_id="expected_requests_delta_total",
        service="TOTAL",
        period="delta",
        estimate=delta_total if (delta_ok and delta_total is not None) else None,
        unit="requests",
        status="ok" if delta_ok else (t_support if not t_ok else b_support),
        identification_status="ok",
        support_status="ok" if delta_ok else (t_support if not t_ok else b_support),
        interval_status=interval_status if delta_ok else "interval_unavailable",
        interval=interval_dict.get("delta_expected_bookings") if delta_ok else None,
        reasons=[] if delta_ok else (b_sup_reasons + t_sup_reasons),
    )

    if not b_ok or not t_ok:
        final_status = t_support if not t_ok else b_support
    else:
        final_status = "ok" if interval_status == "ok" else "interval_unstable"
    all_reasons = reasons + inference_reasons

    output.update(
        status=final_status,
        support_status=support_status,
        interval_status=interval_status,
        interval_level=request.interval_level,
        reasons=all_reasons,
        estimator=bundle.estimator,
        dataset_id=bundle.dataset_id,
        outcome_order=list(bundle.outcome_order),
        treatment_order=list(bundle.treatment_order),
        theta=theta,
        elasticity_at_baseline=elasticity,
        context_blocks=len(selected_contexts),
        context_weight_sessions=int(weights.sum()),
        baseline_multiplier=baseline_multiplier.tolist(),
        target_multiplier=target_multiplier.tolist(),
        delta_log_price=(t1 - t0).tolist(),
        theta_interval=theta_intervals,
        elasticity_interval=elasticity_intervals,
        metrics=metrics,
    )

    if delta_ok:
        output["probabilities"] = {
            label: {
                "before_probability": metrics[f"probability_baseline_{label.lower()}"]["estimate"],
                "after_probability": metrics[f"probability_target_{label.lower()}"]["estimate"],
                "delta_percentage_points": metrics[f"probability_delta_{label.lower()}"][
                    "estimate"
                ],
                "before_expected_choices": (
                    metrics[f"expected_requests_baseline_{label.lower()}"]["estimate"]
                    if label != "NONE"
                    else metrics["expected_non_booking_sessions_baseline"]["estimate"]
                ),
                "after_expected_choices": (
                    metrics[f"expected_requests_target_{label.lower()}"]["estimate"]
                    if label != "NONE"
                    else metrics["expected_non_booking_sessions_target"]["estimate"]
                ),
            }
            for label in ("X", "Y", "NONE")
        }

    if b_ok and total0 is not None:
        output["before_expected_bookings"] = total0
    if t_ok and total1 is not None:
        output["after_expected_bookings"] = total1
    if delta_ok and delta_total is not None:
        output["delta_expected_bookings"] = delta_total
    if interval_dict:
        output["interval"] = {
            name: interval_dict[name]
            for name in [
                f"{label}_{metric}"
                for metric in ("before_probability", "after_probability", "delta_percentage_points")
                for label in ("X", "Y", "NONE")
            ]
            + ["delta_expected_bookings"]
            if name in interval_dict
        }

    return output
