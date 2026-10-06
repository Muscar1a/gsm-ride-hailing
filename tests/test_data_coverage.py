import dataclasses
import importlib

import pytest

from gsm_poc.build_context import build_context
from gsm_poc.build_marts import build_marts
from gsm_poc.build_silver import build_silver

OUTSIDE_JANUARY = (
    {"start": "2023-12-01"},
    {"end": "2024-02-02"},
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


def test_silver_rejects_scope_before_writing_complete_outputs(tlc_fixture):
    config, source = tlc_fixture
    config = dataclasses.replace(
        config, source=dataclasses.replace(config.source, end="2024-02-02")
    )
    with pytest.raises(ValueError, match="TLC adapter covers January 2024 only"):
        build_silver(config, source)
    assert not (config.workspace / "data/silver").exists()


def test_ingest_rejects_scope_before_downloading(tlc_fixture, monkeypatch):
    config, _ = tlc_fixture
    config = dataclasses.replace(
        config, source=dataclasses.replace(config.source, start="2023-12-01")
    )
    module = importlib.import_module("gsm_poc.ingest")

    def unexpected_download(*args):
        pytest.fail("Invalid scope must be rejected before any download")

    monkeypatch.setattr(module, "_download", unexpected_download)
    with pytest.raises(ValueError, match="TLC adapter covers January 2024 only"):
        module.ingest(config)
    assert not (config.workspace / "data/bronze/source_manifest.json").exists()


@pytest.mark.parametrize("builder", (build_marts, build_context))
def test_direct_gold_build_rejects_expanded_scope(tlc_fixture, builder):
    config, source = tlc_fixture
    silver = build_silver(config, source)
    config = dataclasses.replace(
        config, source=dataclasses.replace(config.source, end="2024-02-02")
    )
    with pytest.raises(ValueError, match="TLC adapter covers January 2024 only"):
        builder(config, silver["silver"], silver["build_id"])
    assert not (config.workspace / "data/gold").exists()


def test_silver_rejects_explicit_different_source_month(tlc_fixture):
    config, source = tlc_fixture
    with pytest.raises(ValueError, match="requires the January 2024 source version"):
        build_silver(config, {**source, "source_version": "NYC_TLC_HVFHV_2024-02"})
    assert not (config.workspace / "data/silver").exists()
