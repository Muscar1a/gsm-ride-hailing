"""Complete operational grid and metric-specific denominators."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gsm_poc.core.artifacts import write_frame, write_json
from gsm_poc.core.config import Config
from gsm_poc.data.silver import connection, fetch_required_row


def build_marts(config: Config, silver: Path, build_id: str) -> dict:
    config.source.require_tlc_scope()
    with connection(config) as con:
        con.read_parquet(str(silver)).create_view("silver")
        aggregates = con.execute(
            """
          SELECT PULocationID AS zone_id, slot_start_local, platform,
            count(*) FILTER (WHERE valid_core) AS completed_trip_count,
            count(*) FILTER (WHERE valid_duration) AS n_valid_duration,
            count(*) FILTER (WHERE valid_distance) AS n_valid_distance,
            count(*) FILTER (WHERE valid_price) AS n_valid_price,
            count(*) FILTER (WHERE valid_fare_transaction) AS n_valid_fare_transaction,
            count(*) FILTER (WHERE valid_driver_pay) AS n_valid_driver_pay,
            count(*) FILTER (WHERE valid_wait) AS n_valid_wait,
            quantile_cont(trip_time, 0.5) FILTER (WHERE valid_duration) AS trip_seconds_p50,
            quantile_cont(trip_time, 0.9) FILTER (WHERE valid_duration) AS trip_seconds_p90,
            quantile_cont(trip_km, 0.5) FILTER (WHERE valid_distance) AS trip_km_p50,
            quantile_cont(base_passenger_fare, 0.5) FILTER (WHERE valid_fare_transaction)
                AS base_fare_usd_p50,
            quantile_cont(driver_pay, 0.5) FILTER (WHERE valid_driver_pay) AS driver_pay_usd_p50,
            quantile_cont(request_to_pickup_seconds, 0.5) FILTER (WHERE valid_wait)
                AS request_to_pickup_p50,
            quantile_cont(request_to_pickup_seconds, 0.9) FILTER (WHERE valid_wait)
                AS request_to_pickup_p90,
            count(shared_request_flag_normalized) AS n_shared_request_known,
            count(shared_match_flag_normalized) AS n_shared_match_known,
            avg(cast(shared_request_flag_normalized = 'Y' AS DOUBLE)) AS shared_request_share,
            avg(cast(shared_match_flag_normalized = 'Y' AS DOUBLE)) AS shared_match_share,
            count(*) FILTER (WHERE unknown_dropoff_zone OR unknown_flag_value
                OR duration_difference_warning) AS quality_warning_count
          FROM silver WHERE pickup_datetime < cast(? AS TIMESTAMP)
          GROUP BY PULocationID, slot_start_local, platform
        """,
            [config.source.dashboard_end],
        ).df()
        expected = fetch_required_row(
            con.execute(
                """
          SELECT count(*) FROM silver WHERE valid_core AND pickup_datetime < cast(? AS TIMESTAMP)
        """,
                [config.source.dashboard_end],
            )
        )[0]
    platforms = [{"HV0003": "Uber", "HV0005": "Lyft"}[p] for p in config.source.platforms]
    slots = pd.date_range(
        config.source.start,
        config.source.dashboard_end,
        freq=f"{config.source.slot_minutes}min",
        inclusive="left",
    )
    grid = pd.MultiIndex.from_product(
        [config.source.zones, slots, platforms], names=["zone_id", "slot_start_local", "platform"]
    ).to_frame(index=False)
    mart = grid.merge(
        aggregates,
        how="left",
        on=["zone_id", "slot_start_local", "platform"],
        validate="one_to_one",
    )
    counts = [
        c
        for c in mart
        if c.startswith("n_") or c in ("completed_trip_count", "quality_warning_count")
    ]
    for column in counts:
        mart[column] = mart[column].fillna(0).astype("int64")
    for metric, denominator in (
        ("trip_seconds", "n_valid_duration"),
        ("trip_km", "n_valid_distance"),
        ("base_fare", "n_valid_fare_transaction"),
        ("driver_pay", "n_valid_driver_pay"),
        ("request_to_pickup", "n_valid_wait"),
    ):
        mart[f"{metric}_invalid_or_missing_share"] = 1 - mart[denominator].div(
            mart.completed_trip_count.replace(0, float("nan"))
        )
    mart["low_duration_sample"] = mart.n_valid_duration < config.source.min_group_count
    mart["low_distance_sample"] = mart.n_valid_distance < config.source.min_group_count
    mart["low_fare_sample"] = mart.n_valid_fare_transaction < config.source.min_group_count
    mart["low_driver_pay_sample"] = mart.n_valid_driver_pay < config.source.min_group_count
    mart["low_wait_sample"] = mart.n_valid_wait < config.source.min_group_count
    # Preserve numerators and counts; suppress unstable published quantiles.
    for prefix, low in (
        ("trip_seconds", "low_duration_sample"),
        ("trip_km", "low_distance_sample"),
        ("base_fare", "low_fare_sample"),
        ("driver_pay", "low_driver_pay_sample"),
        ("request_to_pickup", "low_wait_sample"),
    ):
        for column in [c for c in mart if c.startswith(prefix) and c.endswith(("_p50", "_p90"))]:
            mart.loc[mart[low], column] = float("nan")
    mart["source_kind"] = "observed_tlc"
    mart["source_complete"] = True
    actual = int(mart.completed_trip_count.sum())
    if actual != expected:
        raise ValueError(f"Mart count reconciliation failed: {actual} != {expected}")
    path = config.workspace / "data/gold" / build_id / "observed_market_30m.parquet"
    metadata = path.with_suffix(".json")
    write_frame(path, mart)
    write_json(
        metadata,
        {
            "source_kind": "observed_tlc",
            "source_complete": True,
            "build_id": build_id,
            "silver_valid_core_count": expected,
            "mart_completed_trip_count": actual,
            "grid_rows": len(mart),
            "start": config.source.start,
            "end": config.source.dashboard_end,
            "slot_minutes": config.source.slot_minutes,
            "assumed_timezone": config.source.assumed_timezone,
            "units": {"money": "USD", "distance": "km", "duration": "seconds"},
        },
    )
    return {
        "mart": path,
        "mart_metadata": metadata,
        "row_count": len(mart),
        "completed_trip_count": actual,
    }
