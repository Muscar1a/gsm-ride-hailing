"""Train-only contexts with auditable hierarchical fallback."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gsm_poc.artifacts import fingerprint, write_frame, write_json
from gsm_poc.build_silver import connection, fetch_required_row
from gsm_poc.config import Config


def build_context(config: Config, silver: Path, build_id: str) -> dict:
    config.source.require_tlc_scope()
    with connection(config) as con:
        con.execute(
            """
          CREATE TABLE train AS SELECT PULocationID AS zone_id,
            extract(hour FROM pickup_datetime)::INTEGER AS hour,
            extract(isodow FROM pickup_datetime) >= 6 AS is_weekend,
            trip_km, trip_time
          FROM read_parquet(?) WHERE valid_core AND valid_duration AND valid_distance
            AND pickup_datetime < cast(? AS TIMESTAMP)
        """,
            [str(silver), config.source.train_end],
        )
        groupings = ("zone_id, hour, is_weekend", "zone_id, hour", "zone_id", "")
        tables = []
        for keys in groupings:
            prefix = keys + ", " if keys else ""
            suffix = " GROUP BY " + keys if keys else ""
            tables.append(
                con.execute(f"""
              SELECT {prefix}count(*) AS sample_count,
                quantile_cont(trip_km, 0.5) AS distance_km,
                quantile_cont(trip_time, 0.5) AS trip_seconds_p50,
                quantile_cont(trip_time, 0.9) AS trip_seconds_p90 FROM train {suffix}
            """).df()
            )
        minimum, maximum = fetch_required_row(
            con.execute("SELECT min(trip_km), max(trip_km) FROM train")
        )
    if tables[-1].sample_count.iloc[0] < config.source.min_group_count:
        raise ValueError("Insufficient valid training trips even at whole-cluster fallback")
    rows = []
    for zone in config.source.zones:
        for hour in range(24):
            for weekend in (False, True):
                for level, (keys, table) in enumerate(zip(groupings, tables, strict=True)):
                    selected = table
                    for column in keys.split(", ") if keys else []:
                        selected = selected[
                            selected[column]
                            == {"zone_id": zone, "hour": hour, "is_weekend": weekend}[column]
                        ]
                    if (
                        not selected.empty
                        and selected.sample_count.iloc[0] >= config.source.min_group_count
                    ):
                        row = selected.iloc[0].to_dict()
                        row.update(
                            zone_id=zone,
                            hour=hour,
                            is_weekend=weekend,
                            context_id=f"z{zone}-h{hour}-w{int(weekend)}",
                            fallback_level=level,
                            source_kind="observed_tlc",
                        )
                        rows.append(row)
                        break
    contexts = pd.DataFrame(rows)
    lower, upper = float(contexts.distance_km.min()), float(contexts.distance_km.max())
    contexts["distance_scaled"] = (
        (contexts.distance_km - lower) / (upper - lower) if upper > lower else 0.5
    )
    context_id = fingerprint(
        {
            "build_id": build_id,
            "train_end": config.source.train_end,
            "rows": contexts.to_dict("records"),
        }
    )[:20]
    path = config.workspace / "data/gold" / build_id / "context_templates.parquet"
    metadata = path.with_suffix(".json")
    write_frame(path, contexts)
    write_json(
        metadata,
        {
            "context_version": context_id,
            "source_kind": "observed_tlc",
            "fit_start": config.source.start,
            "fit_end_exclusive": config.source.train_end,
            "distance_scale_lower_km": lower,
            "distance_scale_upper_km": upper,
            "observed_trip_distance_min_km": minimum,
            "observed_trip_distance_max_km": maximum,
            "fallback_counts": contexts.fallback_level.value_counts().to_dict(),
            "rows": len(contexts),
            "meaning": "Context of completed TLC trips only",
        },
    )
    return {"contexts": path, "context_metadata": metadata, "context_version": context_id}
