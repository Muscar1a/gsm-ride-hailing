"""DuckDB scan of the scoped source; only aggregates are loaded into pandas."""

from __future__ import annotations

from pathlib import Path

import duckdb

from gsm_poc.artifacts import atomic_path, fingerprint, sha256_file, write_json
from gsm_poc.config import Config
from gsm_poc.validate import FLAG_COLUMNS, TLC_COLUMNS, tlc_schema, zone_lookup


def connection(config: Config) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET memory_limit = ?", [config.source.duckdb_memory_limit])
    con.execute("SET threads = ?", [config.source.threads])
    spill = config.workspace / ".cache/duckdb"
    spill.mkdir(parents=True, exist_ok=True)
    con.execute("SET temp_directory = ?", [str(spill)])
    return con


def copy_parquet(con: duckdb.DuckDBPyConnection, relation: str, path: Path) -> None:
    # relation is an internal constant, never external SQL.
    with atomic_path(path) as temporary:
        con.execute(f"COPY ({relation}) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(temporary)])


def build_silver(config: Config, source: dict) -> dict:
    if not source.get("source_complete"):
        raise ValueError("A complete source manifest is required before building silver")
    trip_path = config.workspace / source["trip_path"]
    zone_path = config.workspace / source["zone_path"]
    if sha256_file(trip_path) != source["trip"]["sha256"]:
        raise ValueError("Source checksum mismatch")
    if sha256_file(zone_path) != source["zones"]["sha256"]:
        raise ValueError("Zone lookup checksum mismatch")
    tlc_schema(trip_path)
    lookup = zone_lookup(zone_path)
    processing_code = {
        name: sha256_file(Path(__file__).with_name(name))
        for name in ("build_silver.py", "build_marts.py", "build_context.py", "validate.py")
    }
    build_id = fingerprint(
        {"source": source, "scope": config.as_dict()["source"], "processing_code": processing_code}
    )[:20]
    silver_path = config.workspace / "data/silver" / build_id / "silver_tlc_trip.parquet"
    quality_path = silver_path.parent / "quality_report.json"
    quarantine_path = silver_path.parent / "quarantined_tlc_trip.parquet"
    with connection(config) as con:
        con.register("zones", lookup)
        con.read_parquet(str(trip_path), file_row_number=True).create_view("raw")
        source_rows = con.execute("SELECT count(*) FROM raw").fetchone()[0]
        missing_core = con.execute("""
            SELECT count(*) FROM raw WHERE pickup_datetime IS NULL
              OR PULocationID IS NULL OR hvfhs_license_num IS NULL
        """).fetchone()[0]
        copy_parquet(
            con,
            """SELECT * FROM raw WHERE pickup_datetime IS NULL
                       OR PULocationID IS NULL OR hvfhs_license_num IS NULL""",
            quarantine_path,
        )
        normalization = ", ".join(
            f"CASE WHEN upper(trim({name})) IN ('Y','N') THEN upper(trim({name})) "
            f"ELSE NULL END AS {name}_normalized"
            for name in FLAG_COLUMNS
        )
        unknown_flags = " OR ".join(
            f"({name} IS NOT NULL AND upper(trim({name})) NOT IN ('Y','N'))"
            for name in FLAG_COLUMNS
        )
        columns = ", ".join(f'r."{name}"' for name in TLC_COLUMNS)
        con.execute(
            f"""
          CREATE TABLE silver AS SELECT {columns},
            ? || ':' || cast(file_row_number AS VARCHAR) AS trip_row_id,
            ? AS source_id, 'observed_tlc' AS source_kind,
            CASE hvfhs_license_num WHEN 'HV0003' THEN 'Uber' WHEN 'HV0005' THEN 'Lyft' END
                AS platform,
            cast(pickup_datetime AS DATE) AS pickup_date_local,
            time_bucket(INTERVAL '{config.source.slot_minutes} minutes', pickup_datetime)
                AS slot_start_local,
            trip_miles * 1.609344 AS trip_km,
            CASE WHEN request_datetime IS NOT NULL AND request_datetime <= pickup_datetime
              THEN date_diff('microsecond', request_datetime, pickup_datetime) / 1000000.0
              ELSE NULL END AS request_to_pickup_seconds,
            date_diff('microsecond', pickup_datetime, dropoff_datetime) / 1000000.0
                AS computed_trip_seconds,
            true AS valid_core,
            coalesce(trip_time > 0 AND dropoff_datetime >= pickup_datetime, false)
                AS valid_duration,
            coalesce(trip_miles >= 0 AND isfinite(trip_miles), false) AS valid_distance,
            coalesce(base_passenger_fare > 0 AND isfinite(base_passenger_fare), false)
                AS valid_price,
            coalesce(isfinite(base_passenger_fare), false) AS valid_fare_transaction,
            coalesce(isfinite(driver_pay), false) AS valid_driver_pay,
            coalesce(request_datetime <= pickup_datetime, false) AS valid_wait,
            coalesce(abs(trip_time - date_diff('microsecond', pickup_datetime, dropoff_datetime)
                / 1000000.0) > ?, false) AS duration_difference_warning,
            pu.LocationID IS NULL AS unknown_pickup_zone,
            do_zone.LocationID IS NULL AS unknown_dropoff_zone,
            ({unknown_flags}) AS unknown_flag_value,
            {normalization},
            CASE WHEN isfinite(base_passenger_fare) AND isfinite(tolls) AND isfinite(bcf)
                AND isfinite(sales_tax) AND isfinite(congestion_surcharge) AND isfinite(airport_fee)
              THEN base_passenger_fare + tolls + bcf + sales_tax
                + congestion_surcharge + airport_fee
              ELSE NULL END AS passenger_components_excluding_tips_usd
          FROM raw r LEFT JOIN zones pu ON r.PULocationID = pu.LocationID
            LEFT JOIN zones do_zone ON r.DOLocationID = do_zone.LocationID
          WHERE pickup_datetime >= cast(? AS TIMESTAMP) AND pickup_datetime < cast(? AS TIMESTAMP)
            AND PULocationID IN (SELECT unnest(?))
            AND hvfhs_license_num IN (SELECT unnest(?))
        """,
            [
                source["source_id"],
                source["source_id"],
                config.source.duration_difference_warning_seconds,
                config.source.start,
                config.source.end,
                list(config.source.zones),
                list(config.source.platforms),
            ],
        )
        scoped = con.execute("SELECT count(*), count(DISTINCT trip_row_id) FROM silver").fetchone()
        if scoped[0] != scoped[1]:
            raise ValueError("Technical row IDs are not unique")
        null_counts = {
            name: con.execute(
                f'SELECT count(*) FILTER (WHERE "{name}" IS NULL) FROM silver'
            ).fetchone()[0]
            for name in TLC_COLUMNS
        }
        flags = (
            "valid_core",
            "valid_duration",
            "valid_distance",
            "valid_price",
            "valid_fare_transaction",
            "valid_driver_pay",
            "valid_wait",
            "duration_difference_warning",
            "unknown_pickup_zone",
            "unknown_dropoff_zone",
            "unknown_flag_value",
        )
        flag_counts = {
            name: con.execute(f"SELECT count(*) FILTER (WHERE {name}) FROM silver").fetchone()[0]
            for name in flags
        }
        duplicate_groups, duplicate_rows = con.execute(f"""
          SELECT count(*), coalesce(sum(n), 0) FROM (
            SELECT count(*) AS n FROM silver GROUP BY {", ".join(TLC_COLUMNS)} HAVING count(*) > 1
          )
        """).fetchone()
        copy_parquet(con, "SELECT * FROM silver", silver_path)
        report = {
            "build_id": build_id,
            "source_id": source["source_id"],
            "source_kind": "observed_tlc",
            "source_complete": True,
            "source_rows": source_rows,
            "scoped_rows": scoped[0],
            "missing_core_rows_entire_source": missing_core,
            "duplicate_content_groups": duplicate_groups,
            "rows_in_duplicate_content_groups": int(duplicate_rows),
            "deduplication_applied": False,
            "null_counts": null_counts,
            "null_count_denominator": scoped[0],
            "flag_counts": flag_counts,
            "scope": config.as_dict()["source"],
            "units": {"money": "USD", "distance": "km", "duration": "seconds"},
        }
        write_json(quality_path, report)
    return {
        "build_id": build_id,
        "silver": silver_path,
        "quality": quality_path,
        "quarantine": quarantine_path,
        "row_count": scoped[0],
    }
