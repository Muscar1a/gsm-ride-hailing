import copy
import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gsm_poc.artifacts import completed_run, read_json, sha256_file, write_json
from gsm_poc.cli import main
from gsm_poc.demand import prepare_demand_plan
from gsm_poc.estimate import fit_estimator
from gsm_poc.features import date_splits
from gsm_poc.generate import generate, save_generated
from gsm_poc.pipeline import Pipeline
from gsm_poc.scenario import ScenarioRequest


@pytest.fixture
def snapshot():
    return read_json(Path(__file__).parents[1] / "configs/week3_snapshot.json")


@pytest.fixture
def demand_inputs(config, exact_blocks):
    splits = date_splits(exact_blocks, config)
    bundle = fit_estimator(splits["train"], config, "adjusted_ols").bundle
    # Unequal, small exposure counts make aggregation/rescaling bugs visible.
    contexts = splits["test"].copy()
    contexts["n_sessions"] = np.where(contexts.zone_id == 161, 40, 80)
    return bundle, contexts


def make_plan(config, snapshot, demand_inputs, **request_values):
    bundle, contexts = demand_inputs
    return prepare_demand_plan(
        bundle,
        contexts,
        snapshot,
        ScenarioRequest(**request_values),
        config,
        "frozen-model",
        "model-sha256",
        "source-sha256",
    )


def test_rates_use_each_block_exposure_and_duration_once(config, snapshot, demand_inputs):
    plan = make_plan(config, snapshot, demand_inputs)
    assert plan.result["usable_for_simulation"]
    assert len(plan.frame) == 4
    assert plan.frame.block_hours.eq(2).all()
    assert set(plan.frame.service_id) == {"X", "Y"}
    x = plan.frame[plan.frame.service_id == "X"]
    y = plan.frame[plan.frame.service_id == "Y"]
    # Known-truth fixture: row X / price X = -0.60, row Y / price X = 0.12.
    assert (x.request_rate - x.baseline_request_rate).to_numpy() == pytest.approx(
        -0.60 * np.log(1.1) * x.quote_sessions.to_numpy() / 2
    )
    assert (y.request_rate - y.baseline_request_rate).to_numpy() == pytest.approx(
        0.12 * np.log(1.1) * y.quote_sessions.to_numpy() / 2
    )
    assert plan.result["summary"]["quote_sessions"] == 120  # shared across X/Y, once
    for block in plan.result["blocks"]:
        assert sum(choice["expected_choices"] for choice in block["choices"].values()) == (
            pytest.approx(block["quote_sessions"])
        )
        assert sum(choice["probability"] for choice in block["choices"].values()) == pytest.approx(
            1
        )
    assert plan.frame.expected_bookings.sum() == pytest.approx(
        sum(
            row["choices"][service]["expected_choices"]
            for row in plan.result["blocks"]
            for service in ("X", "Y")
        )
    )
    assert plan.frame.source_kind.eq("synthetic").all()
    assert plan.snapshot["calibration_status"] == "not_calibrated"
    assert len(plan.snapshot["vehicles"]) == 2
    assert plan.result["interval_status"] == "interval_unavailable"


def test_baseline_and_population_are_preserved(config, snapshot, demand_inputs):
    baseline = make_plan(config, snapshot, demand_inputs, delta_price_x=0, n_sessions=1)
    target = make_plan(config, snapshot, demand_inputs, n_sessions=999999)
    assert baseline.frame.request_rate.to_numpy() == pytest.approx(
        baseline.frame.baseline_request_rate.to_numpy()
    )
    assert baseline.frame.baseline_request_rate.to_numpy() == pytest.approx(
        target.frame.baseline_request_rate.to_numpy()
    )
    alternate = make_plan(config, snapshot, demand_inputs, n_sessions=1)
    pd.testing.assert_frame_equal(alternate.frame, target.frame)
    assert alternate.spec == target.spec
    assert snapshot.get("snapshot_version") is None  # source fixture was not mutated


def test_zero_quotes_and_empty_fleet_do_not_fabricate_demand_or_supply(
    config, snapshot, demand_inputs
):
    bundle, contexts = demand_inputs
    contexts["n_sessions"] = 0
    snapshot["vehicles"] = []
    plan = make_plan(config, snapshot, (bundle, contexts))
    assert plan.result["usable_for_simulation"]
    assert plan.frame.request_rate.eq(0).all()
    assert plan.result["summary"]["quote_sessions"] == 0
    assert plan.snapshot["vehicles"] == []


@pytest.mark.parametrize("failure", ["outside", "thin", "unidentified", "invalid", "validation"])
def test_ineligible_choice_never_becomes_simulator_input(config, snapshot, demand_inputs, failure):
    bundle, contexts = demand_inputs
    request = {}
    expected = {
        "outside": "out_of_support",
        "thin": "insufficient_support",
        "unidentified": "not_identified",
        "invalid": "invalid_probability",
        "validation": "invalid_probability",
    }[failure]
    if failure == "outside":
        request["delta_price_x"] = 0.2
    elif failure == "thin":
        config = dataclasses.replace(
            config, model=dataclasses.replace(config.model, min_price_cell_count=10000)
        )
    elif failure == "unidentified":
        bundle = None
    elif failure == "validation":
        bundle.diagnostics["validation_probability_valid"] = False
    else:
        bundle.base_rate_model.intercept_ = np.array([-0.5, 0.5])
    plan = make_plan(config, snapshot, (bundle, contexts), **request)
    assert plan.result["status"] == expected
    assert not plan.result["usable_for_simulation"]
    assert plan.frame.request_rate.isna().all()
    assert plan.result["summary"]["expected_bookings"] is None
    assert all(block["choices"] is None for block in plan.result["blocks"])


@pytest.mark.parametrize(
    "failure", ["gap", "duplicate", "partial", "negative", "fractional", "string", "boolean"]
)
def test_block_coverage_and_counts_are_validated(config, snapshot, demand_inputs, failure):
    bundle, contexts = demand_inputs
    selected = (contexts.zone_id == 161) & (contexts.slot_start_local == "2024-01-26 08:00")
    if failure == "gap":
        contexts = contexts.loc[~selected]
    elif failure == "duplicate":
        contexts = pd.concat([contexts, contexts.loc[selected]])
    elif failure == "partial":
        snapshot["horizon_end"] = "2024-01-26T09:00:00-05:00"
    elif failure == "negative":
        contexts.loc[selected, "n_sessions"] = -1
    elif failure == "fractional":
        contexts["n_sessions"] = contexts.n_sessions.astype(float)
        contexts.loc[selected, "n_sessions"] = 1.5
    elif failure == "string":
        contexts["n_sessions"] = contexts.n_sessions.astype(str)
    else:
        contexts["n_sessions"] = True
    with pytest.raises(ValueError, match="duplicate|cover|n_sessions"):
        make_plan(config, snapshot, (bundle, contexts))


@pytest.mark.parametrize("failure", ["naive", "offset", "timezone", "soc", "roster", "mode"])
def test_snapshot_rejects_ambiguous_state_and_units(config, snapshot, demand_inputs, failure):
    if failure == "naive":
        snapshot["horizon_start"] = "2024-01-26T08:00:00"
    elif failure == "offset":
        snapshot["horizon_start"] = "2024-01-26T08:00:00+07:00"
    elif failure == "timezone":
        snapshot["timezone"] = "Asia/Bangkok"
    elif failure == "soc":
        snapshot["vehicles"][0]["soc"] = 1.1
    elif failure == "roster":
        snapshot["vehicles"].append(copy.deepcopy(snapshot["vehicles"][0]))
    else:
        snapshot["demand_mode"] = "structural_choice"
    with pytest.raises(ValueError):
        make_plan(config, snapshot, demand_inputs)


@pytest.fixture
def choice_run(config):
    config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    data = generate(config)
    save_generated(config, data)
    pipeline = Pipeline(config, "choice-source")
    pipeline.fit(data.dataset_id)
    pipeline.scenario()
    pipeline.run.complete()
    return pipeline


def test_cli_freezes_source_and_resumes_verified_demand(choice_run, snapshot, monkeypatch, capsys):
    source = choice_run
    source_hash = sha256_file(source.run.manifest_path)
    snapshot_path = source.config.workspace / "snapshot.json"
    write_json(snapshot_path, snapshot)
    monkeypatch.setattr("gsm_poc.cli.Config.load", lambda _: source.config)
    arguments = [
        "prepare-demand",
        "--model-run-id",
        source.run.run_id,
        "--snapshot",
        str(snapshot_path),
        "--run-id",
        "demand-bridge",
    ]
    assert main(arguments) == 0
    manifest = completed_run(source.config.workspace, "demand-bridge")
    assert manifest["stages"]["prepare_demand"]["usable_for_simulation"]
    output = source.config.workspace / "runs/demand-bridge"
    frame = pd.read_parquet(output / "demand_plan.parquet")
    assert len(frame) == 4
    frozen = read_json(output / "demand_bundle/source_manifest.json")
    for relative, checksum in frozen["artifacts"].items():
        suffix = relative.removeprefix(f"runs/{source.run.run_id}/")
        path = output / "demand_bundle" / suffix
        if path.is_file():
            assert sha256_file(path) == checksum
    assert sha256_file(source.run.manifest_path) == source_hash
    capsys.readouterr()
    assert main(arguments) == 0
    assert "prepare_demand: reuse verified artifacts" in capsys.readouterr().out
    assert (
        manifest["stages"]["prepare_demand"]["duration_seconds"]
        == (
            completed_run(source.config.workspace, "demand-bridge")["stages"]["prepare_demand"][
                "duration_seconds"
            ]
        )
    )
    # Changed snapshot must invalidate reuse; shared fleet is still not multiplied by services.
    snapshot["vehicles"][0]["soc"] = 0.7
    write_json(snapshot_path, snapshot)
    assert main(arguments) == 0
    assert "prepare_demand: running" in capsys.readouterr().out
    assert read_json(output / "baseline_snapshot.json")["vehicles"][0]["soc"] == 0.7


def test_source_checksum_failure_is_recorded_before_loading_model(choice_run, snapshot):
    source = choice_run
    snapshot_path = source.config.workspace / "snapshot.json"
    write_json(snapshot_path, snapshot)
    path = source.run.path / "models/adjusted_ols/model_bundle.joblib"
    path.write_bytes(b"corrupt untrusted bytes")
    output = Pipeline(source.config, "bad-demand-source")
    with pytest.raises(ValueError, match="checksum"):
        output.prepare_demand(source.run.run_id, snapshot_path)
    assert output.run.manifest["stages"]["prepare_demand"]["status"] == "failed"
    assert not (output.run.path / "demand_plan.parquet").exists()


def test_frozen_support_threshold_is_not_relaxed_by_current_config(choice_run, snapshot):
    source = choice_run
    source.config = dataclasses.replace(
        source.config, model=dataclasses.replace(source.config.model, min_price_cell_count=10000)
    )
    # Rebuild the source with a genuinely stricter frozen gate; current consumer remains permissive.
    strict = Pipeline(source.config, "strict-choice-source")
    strict.fit(source.run.manifest["dataset_id"])
    strict.scenario()
    strict.run.complete()
    consumer_config = dataclasses.replace(
        strict.config, model=dataclasses.replace(strict.config.model, min_price_cell_count=1)
    )
    snapshot_path = source.config.workspace / "snapshot.json"
    write_json(snapshot_path, snapshot)
    output = Pipeline(consumer_config, "thin-demand-source")
    result = output.prepare_demand(strict.run.run_id, snapshot_path)
    assert result["status"] == "insufficient_support"
    assert not result["usable_for_simulation"]


def test_same_run_cannot_modify_frozen_model_manifest(choice_run, snapshot):
    source_hash = sha256_file(choice_run.run.manifest_path)
    snapshot_path = choice_run.config.workspace / "snapshot.json"
    write_json(snapshot_path, snapshot)
    with pytest.raises(ValueError, match="separate"):
        choice_run.prepare_demand(choice_run.run.run_id, snapshot_path)
    assert sha256_file(choice_run.run.manifest_path) == source_hash
