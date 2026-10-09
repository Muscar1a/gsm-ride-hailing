"""Source-schema and TLC validation checks."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

STRING_COLUMNS = (
    "hvfhs_license_num",
    "dispatching_base_num",
    "originating_base_num",
    "shared_request_flag",
    "shared_match_flag",
    "access_a_ride_flag",
    "wav_request_flag",
    "wav_match_flag",
)
TIMESTAMP_COLUMNS = ("request_datetime", "on_scene_datetime", "pickup_datetime", "dropoff_datetime")
INTEGER_COLUMNS = ("PULocationID", "DOLocationID", "trip_time")
FLOAT_COLUMNS = (
    "trip_miles",
    "base_passenger_fare",
    "tolls",
    "bcf",
    "sales_tax",
    "congestion_surcharge",
    "airport_fee",
    "tips",
    "driver_pay",
)
TLC_COLUMNS = STRING_COLUMNS + TIMESTAMP_COLUMNS + INTEGER_COLUMNS + FLOAT_COLUMNS
FLAG_COLUMNS = STRING_COLUMNS[3:]


def tlc_schema(path: Path) -> dict:
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    if set(schema.names) != set(TLC_COLUMNS) or len(schema) != 24:
        raise ValueError(f"Expected 2024 TLC 24-column schema, got {schema.names}")
    for field in schema:
        kind = field.type
        valid = (
            (
                field.name in STRING_COLUMNS
                and (pa.types.is_string(kind) or pa.types.is_large_string(kind))
            )
            or (field.name in TIMESTAMP_COLUMNS and pa.types.is_timestamp(kind) and kind.tz is None)
            or (field.name in INTEGER_COLUMNS and pa.types.is_integer(kind))
            or (field.name in FLOAT_COLUMNS and pa.types.is_floating(kind))
        )
        if not valid:
            raise ValueError(f"Incompatible TLC field {field.name}: {kind}")
    return {
        "rows": parquet.metadata.num_rows,
        "row_groups": parquet.metadata.num_row_groups,
        "columns": [{"name": f.name, "type": str(f.type), "nullable": f.nullable} for f in schema],
    }


def zone_lookup(path: Path) -> pd.DataFrame:
    zones = pd.read_csv(path)
    if set(zones.columns) != {"LocationID", "Borough", "Zone", "service_zone"}:
        raise ValueError("Unexpected zone lookup schema")
    numeric = pd.to_numeric(zones.LocationID, errors="raise")
    if numeric.isna().any() or (numeric % 1 != 0).any() or numeric.duplicated().any():
        raise ValueError("Zone lookup IDs must be unique non-null integers")
    zones["LocationID"] = numeric.astype("int32")
    return zones
