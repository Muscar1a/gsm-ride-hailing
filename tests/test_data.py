import dataclasses

import pandas as pd
import pytest

from gsm_poc.artifacts import read_json
from gsm_poc.build_context import build_context
from gsm_poc.build_marts import build_marts
from gsm_poc.build_silver import build_silver
from gsm_poc.validate import tlc_schema


def test_silver_keeps_duplicates_and_independent_quality(tlc_fixture):
    config, source = tlc_fixture
    output = build_silver(config, source)
    silver = pd.read_parquet(output["silver"])
    assert len(silver) == 7
    assert silver.trip_row_id.nunique() == 7
    assert silver.trip_row_id.str.endswith(":0").sum() == 1
    assert silver.trip_row_id.str.endswith(":1").sum() == 1
    assert silver.valid_core.all()
    assert silver.valid_wait.sum() == 6
    assert silver.valid_duration.sum() == 6
    assert silver.valid_distance.sum() == 6
    assert silver.valid_fare_transaction.sum() == 7
    assert silver.valid_price.sum() == 6
    assert silver.unknown_dropoff_zone.sum() == 1
    assert silver.unknown_flag_value.sum() == 1
    assert silver.shared_request_flag.iloc[0] == " n "
    assert silver.shared_request_flag_normalized.iloc[0] == "N"
    negative_fare = silver[silver.base_passenger_fare < 0].iloc[0]
    assert pd.isna(negative_fare.passenger_components_excluding_tips_usd)
    assert negative_fare.valid_core
    quality = read_json(output["quality"])
    assert quality["source_rows"] == 9
    assert quality["missing_core_rows_entire_source"] == 1
    assert quality["duplicate_content_groups"] == 1
    assert quality["rows_in_duplicate_content_groups"] == 2
    assert quality["deduplication_applied"] is False


def test_grid_counts_and_empty_cells(tlc_fixture):
    config, source = tlc_fixture
    silver = build_silver(config, source)
    output = build_marts(config, silver["silver"], silver["build_id"])
    mart = pd.read_parquet(output["mart"])
    assert len(mart) == 2 * 2 * 48 * 2
    assert mart.completed_trip_count.sum() == 7
    assert mart.n_valid_wait.sum() == 6
    populated = mart[mart.completed_trip_count > 0].iloc[0]
    assert populated.base_fare_usd_p50 == 10
    assert populated.trip_km_p50 == pytest.approx(2 * 1.609344)
    assert populated.request_to_pickup_p50 == 60
    empty = mart[mart.completed_trip_count == 0]
    assert empty.source_complete.all()
    assert empty.trip_seconds_p50.isna().all()
    assert empty.request_to_pickup_invalid_or_missing_share.isna().all()


def test_context_is_train_only_and_fallback_is_recorded(tlc_fixture):
    config, source = tlc_fixture
    silver = build_silver(config, source)
    output = build_context(config, silver["silver"], silver["build_id"])
    contexts = pd.read_parquet(output["contexts"])
    assert len(contexts) == 2 * 24 * 2
    assert contexts.distance_scaled.between(0, 1).all()
    assert contexts.sample_count.min() >= 1
    assert set(contexts.fallback_level) >= {0, 1, 2, 3}
    metadata = read_json(output["context_metadata"])
    assert metadata["fit_end_exclusive"] == "2024-01-21"


def test_schema_rejects_2025_or_incomplete_columns(tmp_path):
    path = tmp_path / "bad.parquet"
    pd.DataFrame({"cbd_congestion_fee": [0.0]}).to_parquet(path)
    with pytest.raises(ValueError, match="24-column"):
        tlc_schema(path)


def test_low_sample_quantiles_suppressed_without_losing_counts(tlc_fixture):
    config, source = tlc_fixture
    config = dataclasses.replace(
        config, source=dataclasses.replace(config.source, min_group_count=30)
    )
    silver = build_silver(config, source)
    output = build_marts(config, silver["silver"], silver["build_id"])
    mart = pd.read_parquet(output["mart"])
    assert mart.completed_trip_count.sum() == 7
    assert mart.trip_seconds_p50.isna().all()
    assert mart.base_fare_usd_p50.isna().all()


def test_incomplete_source_and_tampered_source_are_rejected(tlc_fixture):
    config, source = tlc_fixture
    with pytest.raises(ValueError, match="complete source"):
        build_silver(config, {**source, "source_complete": False})
    with pytest.raises(ValueError, match="checksum"):
        build_silver(config, {**source, "trip": {"sha256": "incorrect"}})


def test_download_resumes_after_second_file_failure(tlc_fixture, monkeypatch):
    import importlib
    import shutil

    from gsm_poc.artifacts import sha256_file

    module = importlib.import_module("gsm_poc.ingest")
    config, source = tlc_fixture
    fixture_trip = config.workspace / source["trip_path"]
    fixture_zones = config.workspace / source["zone_path"]
    calls = []

    def download(url, target, config):
        calls.append(url)
        if url == config.source.zone_url and calls.count(url) == 1:
            raise OSError("Connection interrupted")
        shutil.copyfile(fixture_trip if url == config.source.trip_url else fixture_zones, target)
        return {"url": url, "bytes": target.stat().st_size, "sha256": sha256_file(target)}

    monkeypatch.setattr(module, "_download", download)
    with pytest.raises(OSError, match="Connection interrupted"):
        module.ingest(config)
    result = module.ingest(config)
    assert result["source_complete"]
    assert calls.count(config.source.trip_url) == 1
    assert calls.count(config.source.zone_url) == 2
