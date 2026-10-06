import dataclasses
import importlib

import pandas as pd
import pytest

from gsm_poc.build_context import build_context
from gsm_poc.build_marts import build_marts
from gsm_poc.build_silver import build_silver
from gsm_poc.config import TLC_SOURCE_VERSION

OUTSIDE_JANUARY = (
    {"start": "2023-12-01"},
    {"end": "2024-02-02"},
    {"end": "2024-02-02", "dashboard_end": "2024-02-02"},
)


@pytest.mark.parametrize("scope", OUTSIDE_JANUARY)
def test_tlc_config_rejects_scope_outside_downloaded_month(config, scope):
    with pytest.raises(ValueError, match="TLC adapter covers January 2024 only"):
        dataclasses.replace(
            config,
            project=dataclasses.replace(config.project, context_mode="tlc"),
            source=dataclasses.replace(config.source, **scope),
        )


@pytest.mark.parametrize("scope", OUTSIDE_JANUARY)
def test_synthetic_config_keeps_date_flexibility(config, scope):
    updated = dataclasses.replace(config, source=dataclasses.replace(config.source, **scope))
    assert updated.project.context_mode == "synthetic"
    for field, value in scope.items():
        assert getattr(updated.source, field) == value


@pytest.mark.parametrize("scope", OUTSIDE_JANUARY)
def test_silver_rejects_scope_before_writing_complete_outputs(tlc_fixture, scope):
    config, source = tlc_fixture
    config = dataclasses.replace(config, source=dataclasses.replace(config.source, **scope))
    with pytest.raises(ValueError, match="TLC adapter covers January 2024 only"):
        build_silver(config, source)
    assert not (config.workspace / "data/silver").exists()


@pytest.mark.parametrize("scope", OUTSIDE_JANUARY)
def test_ingest_rejects_scope_before_downloading(tlc_fixture, monkeypatch, scope):
    config, _ = tlc_fixture
    config = dataclasses.replace(config, source=dataclasses.replace(config.source, **scope))
    module = importlib.import_module("gsm_poc.ingest")

    def unexpected_download(*args):
        pytest.fail("Invalid scope must be rejected before any download")

    monkeypatch.setattr(module, "_download", unexpected_download)
    with pytest.raises(ValueError, match="TLC adapter covers January 2024 only"):
        module.ingest(config)
    assert not (config.workspace / "data/bronze/source_manifest.json").exists()


@pytest.mark.parametrize("builder", (build_marts, build_context))
@pytest.mark.parametrize("scope", OUTSIDE_JANUARY)
def test_direct_gold_build_rejects_expanded_scope(tlc_fixture, builder, scope):
    config, source = tlc_fixture
    silver = build_silver(config, source)
    config = dataclasses.replace(config, source=dataclasses.replace(config.source, **scope))
    with pytest.raises(ValueError, match="TLC adapter covers January 2024 only"):
        builder(config, silver["silver"], silver["build_id"])
    assert not (config.workspace / "data/gold").exists()


def test_silver_rejects_explicit_different_source_month(tlc_fixture):
    config, source = tlc_fixture
    with pytest.raises(ValueError, match="requires the January 2024 source version"):
        build_silver(config, {**source, "source_version": "NYC_TLC_HVFHV_2024-02"})
    assert not (config.workspace / "data/silver").exists()


def test_empty_day_inside_source_month_remains_a_complete_zero(tlc_fixture):
    config, source = tlc_fixture
    config = dataclasses.replace(
        config, project=dataclasses.replace(config.project, context_mode="tlc")
    )
    silver = build_silver(config, {**source, "source_version": TLC_SOURCE_VERSION})
    output = build_marts(config, silver["silver"], silver["build_id"])
    mart = pd.read_parquet(output["mart"])
    empty_day = mart[mart.slot_start_local.dt.date == pd.Timestamp("2024-01-02").date()]
    assert len(empty_day) == 2 * 48 * 2
    assert empty_day.completed_trip_count.eq(0).all()
    assert empty_day.source_complete.all()
    assert empty_day.trip_seconds_p50.isna().all()
