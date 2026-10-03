from __future__ import annotations

import dataclasses
import datetime as dt

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from gsm_poc.artifacts import sha256_file
from gsm_poc.config import Config, EvaluationConfig, ModelConfig, SimulationConfig, SourceConfig
from gsm_poc.generate import generate
from gsm_poc.validate import FLOAT_COLUMNS, INTEGER_COLUMNS, STRING_COLUMNS, TIMESTAMP_COLUMNS


@pytest.fixture
def config(tmp_path):
    return Config(
        workspace=tmp_path,
        source=SourceConfig(zones=(161, 162), min_group_count=1),
        simulation=SimulationConfig(slot_minutes=120),
        model=ModelConfig(n_trees=5, min_samples_leaf=5, min_price_cell_count=1),
        evaluation=EvaluationConfig(
            seeds=2, bootstrap_draws=3, dgps=("RCT_SYN", "COLLINEAR_PRICE")
        ),
    )


@pytest.fixture
def generated(config):
    return generate(config)


@pytest.fixture
def exact_blocks(generated):
    # Deterministic conditional means provide a numerical oracle fixture only in tests.
    frame = generated.blocks.copy()
    frame["q_x"] = generated.oracle.p_x.to_numpy()
    frame["q_y"] = generated.oracle.p_y.to_numpy()
    frame["q_none"] = generated.oracle.p_none.to_numpy()
    return frame


@pytest.fixture
def tlc_fixture(config):
    config = dataclasses.replace(
        config, source=dataclasses.replace(config.source, dashboard_end="2024-01-03")
    )
    bronze = config.workspace / "data/bronze"
    bronze.mkdir(parents=True)
    rows = []
    for i in range(9):
        pickup = dt.datetime(2024, 1, 1, 0, i)
        row = {c: "N" for c in STRING_COLUMNS}
        row.update({c: 1.0 for c in FLOAT_COLUMNS})
        row.update({c: 161 for c in INTEGER_COLUMNS})
        row.update({c: pickup for c in TIMESTAMP_COLUMNS})
        row.update(
            hvfhs_license_num="HV0003",
            dispatching_base_num="B1",
            originating_base_num=None,
            PULocationID=161,
            DOLocationID=162,
            request_datetime=pickup - dt.timedelta(seconds=60),
            dropoff_datetime=pickup + dt.timedelta(seconds=600),
            trip_time=600,
            trip_miles=2.0,
            base_passenger_fare=10.0,
            driver_pay=6.0,
            shared_request_flag=" n ",
        )
        rows.append(row)
    rows[1] = rows[0].copy()  # identical public attributes, distinct physical rows
    rows[2]["request_datetime"] = rows[2]["pickup_datetime"] + dt.timedelta(seconds=1)
    rows[3]["base_passenger_fare"] = -2.0
    rows[3]["tolls"] = None
    rows[4]["trip_time"] = -1
    rows[5]["trip_miles"] = -1.0
    rows[6]["DOLocationID"] = 999
    rows[6]["shared_match_flag"] = "UNKNOWN"
    rows[7]["pickup_datetime"] = None
    rows[8]["PULocationID"] = 999  # out of pickup scope
    fields = [
        *(pa.field(c, pa.large_string()) for c in STRING_COLUMNS),
        *(pa.field(c, pa.timestamp("us")) for c in TIMESTAMP_COLUMNS),
        *(pa.field(c, pa.int64() if c == "trip_time" else pa.int32()) for c in INTEGER_COLUMNS),
        *(pa.field(c, pa.float64()) for c in FLOAT_COLUMNS),
    ]
    trip = bronze / "fixture.parquet"
    zones = bronze / "zones.csv"
    pq.write_table(pa.Table.from_pylist(rows, schema=pa.schema(fields)), trip)
    pd.DataFrame(
        {
            "LocationID": [161, 162],
            "Borough": ["Manhattan", "Manhattan"],
            "Zone": ["Midtown Center", "Midtown East"],
            "service_zone": ["Yellow", "Yellow"],
        }
    ).to_csv(zones, index=False)
    digest = sha256_file(trip)
    source = {
        "source_id": digest,
        "source_complete": True,
        "source_kind": "test_fixture",
        "trip": {"sha256": digest},
        "zones": {"sha256": sha256_file(zones)},
        "trip_path": str(trip.relative_to(config.workspace)),
        "zone_path": str(zones.relative_to(config.workspace)),
    }
    return config, source
