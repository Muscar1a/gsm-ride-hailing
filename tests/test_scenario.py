import dataclasses
from itertools import product

import numpy as np
import pandas as pd
import pytest
from gsm_poc.estimate import fit_estimator
from gsm_poc.features import date_splits
from gsm_poc.scenario import ScenarioRequest, joint_support, scenario
from gsm_poc.uncertainty import BootstrapResult


@pytest.fixture
def fitted(config, exact_blocks):
    splits = date_splits(exact_blocks, config)
    bundle = fit_estimator(splits["train"], config, "adjusted_ols").bundle
    if bundle.train_support is not None and not bundle.train_support.empty:
        group_columns = ["zone_id", "is_weekend", "is_peak"]
        groups = splits["test"][group_columns].drop_duplicates()
        extra_rows = []
        for row in groups.itertuples(index=False):
            for x, y in product((0.9, 1.0, 1.1), (0.9, 1.0, 1.1)):
                sel = bundle.train_support[
                    (bundle.train_support.zone_id == row.zone_id)
                    & (bundle.train_support.is_weekend == row.is_weekend)
                    & (bundle.train_support.is_peak == row.is_peak)
                    & np.isclose(bundle.train_support.multiplier_x, x)
                    & np.isclose(bundle.train_support.multiplier_y, y)
                ]
                if sel.empty:
                    extra_rows.append(
                        {
                            "zone_id": row.zone_id,
                            "is_weekend": row.is_weekend,
                            "is_peak": row.is_peak,
                            "multiplier_x": x,
                            "multiplier_y": y,
                        }
                    )
        if extra_rows:
            bundle.train_support = pd.concat(
                [bundle.train_support, pd.DataFrame(extra_rows)], ignore_index=True
            )
    return bundle, splits["test"]


def test_plus10_log_ratio_orientation_and_count_conservation(config, fitted):
    bundle, context = fitted
    result = scenario(
        bundle, context, ScenarioRequest(), config, "test-run", inference_method="bootstrap"
    )
    values = result["probabilities"]
    assert values["X"]["delta_percentage_points"] == pytest.approx(-0.60 * np.log(1.1) * 100)
    assert values["Y"]["delta_percentage_points"] == pytest.approx(0.12 * np.log(1.1) * 100)
    assert result["delta_expected_bookings"] == pytest.approx(-0.48 * np.log(1.1) * 10000)
    assert sum(v["before_probability"] for v in values.values()) == pytest.approx(1)
    assert sum(v["after_expected_choices"] for v in values.values()) == pytest.approx(10000)
    assert result["evidence_level"] == "C"
    assert result["target_context_set"] == "all"
    assert result["scope"]["target_context_set"] == "all"
    assert result["scope"]["zones"] == sorted(context.zone_id.unique())
    assert result["scope"]["context_blocks"] == len(context)
    assert result["scope"]["context_weight_sessions"] == int(context.n_sessions.sum())
    assert result["request"]["target_context_set"] == "all"
    assert result["interval"] is None
    assert result["bootstrap"]["interval_status"] == "interval_unstable"


def test_price_y_is_second_column_and_unchanged_prices_zero_effect(config, fitted):
    bundle, context = fitted
    result = scenario(
        bundle, context, ScenarioRequest(delta_price_x=0, delta_price_y=0.1), config, "test-run"
    )
    assert result["probabilities"]["X"]["delta_percentage_points"] == pytest.approx(
        0.15 * np.log(1.1) * 100
    )
    result = scenario(
        bundle, context, ScenarioRequest(delta_price_x=0, delta_price_y=0), config, "test-run"
    )
    assert result["delta_expected_bookings"] == pytest.approx(0)


def test_outside_joint_support_has_no_forecast(config, fitted):
    bundle, context = fitted
    result = scenario(bundle, context, ScenarioRequest(delta_price_x=0.2), config, "test-run")
    assert result["status"] == "out_of_support"
    assert "probabilities" not in result
    bundle.train_support = bundle.train_support[
        ~((bundle.train_support.multiplier_x == 1.1) & (bundle.train_support.multiplier_y == 1.0))
    ]
    result = scenario(bundle, context, ScenarioRequest(), config, "test-run")
    assert result["status"] == "out_of_support"


def test_invalid_probability_rejected_without_clipping(config, fitted):
    bundle, context = fitted
    bundle.base_rate_model.intercept_ = np.array([-0.1, 0.5])
    result = scenario(bundle, context, ScenarioRequest(), config, "test-run")
    assert result["status"] == "invalid_probability"
    assert "probabilities" not in result


def test_bad_draws_are_counted_and_interval_withheld(config, fitted):
    bundle, context = fitted
    invalid = dataclasses.replace(bundle)
    invalid.base_rate_model = dataclasses.replace(bundle).base_rate_model.__class__()
    invalid.base_rate_model.__dict__.update(bundle.base_rate_model.__dict__)
    invalid.base_rate_model.intercept_ = np.array([-0.5, 0.5])
    draws = BootstrapResult("adjusted_ols", [], [bundle, invalid, None], "ok", 3, 0.95)
    result = scenario(
        bundle, context, ScenarioRequest(), config, "test-run", draws, inference_method="bootstrap"
    )
    assert result["bootstrap"]["invalid_probability_draws"] == 1
    assert result["bootstrap"]["fit_failed_draws"] == 1
    assert result["bootstrap"]["failure_fraction"] == pytest.approx(2 / 3)
    assert result["interval"] is None


@pytest.mark.parametrize(
    "scenario_request",
    [
        ScenarioRequest(delta_price_x=-1),
        ScenarioRequest(delta_price_x=float("nan")),
        ScenarioRequest(n_sessions=0),
        ScenarioRequest(target_context_set=""),
        ScenarioRequest(target_context_set="   "),
    ],
)
def test_invalid_request_rejected(config, fitted, scenario_request):
    bundle, context = fitted
    with pytest.raises(ValueError):
        scenario(bundle, context, scenario_request, config, "test-run")


def test_scenario_saves_custom_scope_and_selected_zone(config, fitted):
    bundle, context = fitted
    selected = context[context.zone_id == 161]
    request = ScenarioRequest(target_context_set="zone_161")
    result = scenario(bundle, selected, request, config, "test-run")
    assert result["target_context_set"] == "zone_161"
    assert result["scope"]["target_context_set"] == "zone_161"
    assert result["scope"]["zones"] == [161]
    assert result["scope"]["selected_zone"] == 161
    assert result["scope"]["context_blocks"] == len(selected)
    assert result["scope"]["context_weight_sessions"] == int(selected.n_sessions.sum())
    assert result["request"]["target_context_set"] == "zone_161"


@pytest.mark.parametrize(
    ("selected_count", "target_x"),
    [(0, 1.1), (19, 1.1), (20, 1.1), (19, 1.05), (20, 1.05)],
)
def test_support_counts_each_selected_context_at_each_price_corner(
    config, fitted, selected_count, target_x
):
    bundle, context = fitted
    config = dataclasses.replace(
        config, model=dataclasses.replace(config.model, min_price_cell_count=20)
    )
    # A fully supported synthetic table except for one selected group/corner.
    rows = []
    for zone, weekend, peak, x, y in product(
        config.source.zones, (0, 1), (0, 1), (0.9, 1.0, 1.1), (0.9, 1.0, 1.1)
    ):
        count = selected_count if (zone, weekend, peak, x, y) == (161, 0, 0, 1.1, 1.0) else 20
        rows.extend(
            [
                {
                    "zone_id": zone,
                    "is_weekend": weekend,
                    "is_peak": peak,
                    "multiplier_x": x,
                    "multiplier_y": y,
                }
            ]
            * count
        )
    bundle.train_support = pd.DataFrame(rows)
    status, reasons = joint_support(bundle, context, np.array([target_x, 1.0]), config)
    if selected_count < 20:
        assert status == "insufficient_support"
        assert any(
            "zone_id=161" in reason and f"{selected_count} blocks" in reason for reason in reasons
        )
        forecast = scenario(
            bundle, context, ScenarioRequest(delta_price_x=target_x - 1), config, "support-test"
        )
        assert forecast["status"] == "insufficient_support"
        assert forecast["support_status"] == "insufficient_support"
    else:
        assert status == "ok"
        assert not reasons
    # A thin unselected group does not penalize an independently supported zone.
    status, reasons = joint_support(
        bundle, context[context.zone_id == 162], np.array([target_x, 1.0]), config
    )
    assert status == "ok"
    assert not reasons


def test_saved_bundle_with_failed_validation_has_no_forecast(config, fitted):
    bundle, context = fitted
    # Test probabilities are valid; the validation failure must still block this model.
    bundle.diagnostics["validation_probability_valid"] = False
    result = scenario(bundle, context, ScenarioRequest(), config, "failed-validation")
    assert result["status"] == "invalid_probability"
    assert any("validation" in reason.lower() for reason in result["reasons"])
    assert "probabilities" not in result
    assert "theta" not in result


def test_forecast_contract_schema_v2_and_csv_generation(config, fitted):
    from gsm_poc.causal.forecast_contract import format_scenario_metrics_csv

    bundle, context = fitted
    result = scenario(
        bundle, context, ScenarioRequest(), config, "schema2-test", inference_method="bootstrap"
    )
    assert result["schema_version"] == 2
    assert "scope" in result
    assert "provenance" in result
    assert "identification" in result
    assert "support" in result
    assert "evidence" in result
    assert "metrics" in result
    assert "probabilities" in result  # compatibility alias
    assert "before_expected_bookings" in result
    assert "after_expected_bookings" in result
    assert "delta_expected_bookings" in result

    metrics = result["metrics"]
    assert "probability_baseline_x" in metrics
    assert "probability_target_x" in metrics
    assert "probability_delta_x" in metrics
    assert "expected_requests_baseline_total" in metrics
    assert "expected_requests_target_total" in metrics
    assert "expected_requests_delta_total" in metrics

    assert metrics["probability_baseline_x"]["unit"] == "fraction"
    assert metrics["probability_delta_x"]["unit"] == "percentage_points"
    assert metrics["expected_requests_baseline_total"]["unit"] == "requests"
    assert metrics["expected_requests_delta_total"]["estimate"] == pytest.approx(
        result["delta_expected_bookings"]
    )
    assert "expected_non_booking_sessions_target" in metrics
    assert metrics["expected_non_booking_sessions_target"]["unit"] == "non_booking_sessions"
    assert metrics["expected_non_booking_sessions_target"]["service"] == "NONE"
    assert "expected_requests_target_none" not in metrics

    csv_text = format_scenario_metrics_csv(result)
    assert "metric_id,service,period,estimate,unit,status" in csv_text
    assert "probability_baseline_x,X,baseline" in csv_text
    assert "expected_requests_delta_total,TOTAL,delta" in csv_text
    assert "expected_non_booking_sessions_target,NONE,target" in csv_text
    assert "expected_requests_target_none" not in csv_text


def test_scenario_horizon_selection_and_validation(config, fitted):
    from gsm_poc.causal.forecast_contract import parse_horizon_timestamp

    bundle, context = fitted
    ctx = context.copy()
    # Set slot_start_local to explicit known timestamps in America/New_York
    base_time = pd.Timestamp("2026-03-01 00:00:00")
    slot_hours = int(config.simulation.slot_minutes / 60.0)
    # Generate continuous blocks for each zone
    zones = sorted(ctx.zone_id.unique())
    n_blocks_per_zone = len(ctx) // len(zones)
    new_starts = []
    for _ in zones:
        for i in range(n_blocks_per_zone):
            new_starts.append(str(base_time + pd.Timedelta(hours=i * slot_hours)))
    ctx["slot_start_local"] = new_starts

    # Horizon covering exactly first 2 blocks (00:00 to 04:00)
    h_start = "2026-03-01T00:00:00-05:00"
    h_end = "2026-03-01T04:00:00-05:00"
    req = ScenarioRequest(horizon_start=h_start, horizon_end=h_end)
    result = scenario(bundle, ctx, req, config, "horizon-test")

    assert result["scope"]["horizon_start"] == h_start
    assert result["scope"]["horizon_end"] == h_end
    assert result["scope"]["timezone"] == "America/New_York"
    assert result["scope"]["context_blocks"] == 2 * len(zones)

    # Test DST or offset mismatch detection
    with pytest.raises(ValueError, match="DST mismatch"):
        parse_horizon_timestamp("2026-03-01T00:00:00+00:00", "America/New_York", "horizon_start")

    # Incomplete range raises error
    with pytest.raises(ValueError, match="both be provided"):
        ScenarioRequest(horizon_start=h_start, horizon_end=None).validate()


def test_insufficient_support_gates_target_and_delta_metrics_for_all_estimators(config, fitted):
    bundle, context = fitted
    config = dataclasses.replace(
        config, model=dataclasses.replace(config.model, min_price_cell_count=20)
    )
    # Synthetic table where baseline (1.0, 1.0) has 20 blocks,
    # but target (1.1, 1.0) has only 10 blocks in zone 161
    rows = []
    for zone, weekend, peak, x, y in product(
        config.source.zones, (0, 1), (0, 1), (0.9, 1.0, 1.1), (0.9, 1.0, 1.1)
    ):
        count = 10 if (zone, weekend, peak, x, y) == (161, 0, 0, 1.1, 1.0) else 20
        rows.extend(
            [
                {
                    "zone_id": zone,
                    "is_weekend": weekend,
                    "is_peak": peak,
                    "multiplier_x": x,
                    "multiplier_y": y,
                }
            ]
            * count
        )
    bundle.train_support = pd.DataFrame(rows)

    result = scenario(
        bundle, context, ScenarioRequest(delta_price_x=0.10), config, "insufficient-test"
    )
    assert result["status"] == "insufficient_support"
    assert result["support_status"] == "insufficient_support"
    assert "after_expected_bookings" not in result
    assert "delta_expected_bookings" not in result
    assert "probabilities" not in result
    assert result["before_expected_bookings"] > 0

    metrics = result["metrics"]
    # Baseline is ok and has value
    assert metrics["expected_requests_baseline_total"]["status"] == "ok"
    assert metrics["expected_requests_baseline_total"]["estimate"] is not None
    assert metrics["expected_requests_baseline_total"]["estimate"] > 0

    # Target and delta lack support and have None estimates
    assert metrics["expected_requests_target_total"]["status"] == "insufficient_support"
    assert metrics["expected_requests_target_total"]["estimate"] is None
    assert metrics["expected_requests_delta_total"]["status"] == "insufficient_support"
    assert metrics["expected_requests_delta_total"]["estimate"] is None
    assert metrics["probability_target_x"]["status"] == "insufficient_support"
    assert metrics["probability_target_x"]["estimate"] is None
    assert metrics["probability_delta_x"]["status"] == "insufficient_support"
    assert metrics["probability_delta_x"]["estimate"] is None


def test_select_scenario_contexts_detects_missing_zone_in_all_zones_horizon(config, fitted):
    from gsm_poc.causal.forecast_contract import select_scenario_contexts

    bundle, context = fitted
    ctx = context.copy()
    base_time = pd.Timestamp("2026-04-01 00:00:00")
    slot_hours = int(config.simulation.slot_minutes / 60.0)
    # Zone 161 has blocks starting at 2026-04-01 00:00:00
    # Zone 162 has blocks starting only at 2026-04-06 00:00:00
    new_starts = []
    zone_counts = {161: 0, 162: 0}
    for _, row in ctx.iterrows():
        z = int(row.zone_id)
        offset_day = 0 if z == 161 else 5
        idx = zone_counts[z]
        zone_counts[z] += 1
        new_starts.append(str(base_time + pd.Timedelta(days=offset_day, hours=idx * slot_hours)))
    ctx["slot_start_local"] = new_starts

    # Requested horizon covers 2026-04-01 00:00 to 04:00 (zone 162 has no blocks here)
    h_start = "2026-04-01T00:00:00-04:00"
    h_end = "2026-04-01T04:00:00-04:00"
    with pytest.raises(
        ValueError, match="Zone 162 has no context blocks covering the requested horizon"
    ):
        select_scenario_contexts(
            ctx,
            target_context_set="all",
            horizon_start=h_start,
            horizon_end=h_end,
            timezone="America/New_York",
            slot_minutes=config.simulation.slot_minutes,
        )


def test_bootstrap_invalid_probability_draw_marks_diagnostics_unstable(config, fitted):
    from unittest.mock import MagicMock

    bundle, context = fitted
    # Valid draw with probabilities inside simplex
    valid_draw = MagicMock()
    valid_draw.probabilities.return_value = np.column_stack(
        [np.full((len(context), 2), 0.3), np.full((len(context), 1), 0.4)]
    )
    valid_draw.theta = np.array([[-0.6, 0.15], [0.12, -0.5]])

    # Invalid draw with negative probability
    invalid_draw = MagicMock()
    invalid_draw.probabilities.return_value = np.column_stack(
        [np.full((len(context), 1), -0.2), np.full((len(context), 2), 0.6)]
    )
    invalid_draw.theta = np.array([[-0.6, 0.15], [0.12, -0.5]])

    # 199 valid draws + 1 invalid draw (200 total requested)
    draws = BootstrapResult(
        estimator="adjusted_ols",
        records=[],
        bundles=[valid_draw] * 199 + [invalid_draw],
        interval_status="ok",
        requested_draws=200,
        interval_level=0.95,
    )

    result = scenario(
        bundle,
        context,
        ScenarioRequest(delta_price_x=0.1, delta_price_y=0.0, target_context_set="all"),
        config,
        "test_run",
        draws=draws,
        inference_method="bootstrap",
    )

    assert result["bootstrap"]["invalid_probability_draws"] == 1
    assert result["bootstrap"]["interval_status"] == "interval_unstable"
    assert result["interval_status"] == "interval_unstable"
    assert result["interval"] is None


def test_non_booking_sessions_exported_as_non_booking_unit_and_summing_services_matches_total(
    config, fitted
):
    bundle, context = fitted
    result = scenario(
        bundle,
        context,
        ScenarioRequest(delta_price_x=0.1, delta_price_y=0.0, target_context_set="all"),
        config,
        "test_run",
        inference_method="bootstrap",
    )
    m = result["metrics"]

    # Request metrics exist strictly for X, Y, and TOTAL
    for period in ("baseline", "target", "delta"):
        assert f"expected_requests_{period}_x" in m
        assert f"expected_requests_{period}_y" in m
        assert f"expected_requests_{period}_total" in m
        assert f"expected_requests_{period}_none" not in m
        assert m[f"expected_requests_{period}_x"]["unit"] == "requests"
        assert m[f"expected_requests_{period}_y"]["unit"] == "requests"
        assert m[f"expected_requests_{period}_total"]["unit"] == "requests"

        # Non-booking sessions exist strictly for NONE with unit non_booking_sessions
        assert f"expected_non_booking_sessions_{period}" in m
        assert m[f"expected_non_booking_sessions_{period}"]["unit"] == "non_booking_sessions"
        assert m[f"expected_non_booking_sessions_{period}"]["service"] == "NONE"

    # Summing service rows where unit == 'requests' equals total requests
    req_x = m["expected_requests_target_x"]["estimate"]
    req_y = m["expected_requests_target_y"]["estimate"]
    req_total = m["expected_requests_target_total"]["estimate"]
    assert req_x + req_y == pytest.approx(req_total)
