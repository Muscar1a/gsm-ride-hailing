"""Bounded downloads with immutable source bytes and explicit completeness."""

from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from pathlib import Path

from gsm_poc.core.artifacts import atomic_path, read_json, sha256_file, utc_now, write_json
from gsm_poc.core.config import TLC_SOURCE_VERSION, Config
from gsm_poc.data.validate import tlc_schema, zone_lookup


def _download(url: str, target: Path, config: Config) -> dict:
    if not url.startswith("https://"):
        raise ValueError("Source downloads require HTTPS")
    last_error = None
    for attempt in range(config.source.download_retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "gsm-poc/0.1"})
            with atomic_path(target) as temporary:
                with (
                    urllib.request.urlopen(
                        request, timeout=config.source.download_timeout_seconds
                    ) as response,
                    temporary.open("wb") as stream,
                ):
                    length = response.headers.get("Content-Length")
                    expected = int(length) if length is not None else None
                    if expected is not None and expected > config.source.max_download_bytes:
                        raise ValueError("Source exceeds configured download byte budget")
                    digest = hashlib.sha256()
                    size = 0
                    for chunk in iter(lambda: response.read(1024 * 1024), b""):
                        size += len(chunk)
                        if size > config.source.max_download_bytes:
                            raise ValueError("Download exceeded configured byte budget")
                        digest.update(chunk)
                        stream.write(chunk)
                    if size == 0 or (expected is not None and size != expected):
                        raise OSError(
                            f"Incomplete source: expected {expected} bytes, received {size}"
                        )
            return {
                "url": url,
                "downloaded_at": utc_now(),
                "bytes": size,
                "sha256": digest.hexdigest(),
                "http_content_length": expected,
            }
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt + 1 < config.source.download_retries:
                time.sleep(min(attempt + 1, 3))
    raise OSError(
        f"Download failed after {config.source.download_retries} attempts: {url}"
    ) from last_error


def ingest(config: Config) -> dict:
    config.source.require_tlc_scope()
    bronze = config.workspace / "data/bronze"
    manifest_path = bronze / "source_manifest.json"
    trip_path = bronze / "fhvhv_tripdata_2024-01.parquet"
    zone_path = bronze / "taxi_zone_lookup.csv"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        for key, path, url in (
            ("trip", trip_path, config.source.trip_url),
            ("zones", zone_path, config.source.zone_url),
        ):
            record = manifest[key]
            if record["url"] != url or not path.exists() or sha256_file(path) != record["sha256"]:
                raise ValueError(
                    "Bronze source mismatch; preserve it and select a separate workspace"
                )
        tlc_schema(trip_path)
        zone_lookup(zone_path)
        return manifest

    def fetch(url: str, path: Path) -> dict:
        receipt = path.with_suffix(path.suffix + ".source.json")
        if receipt.exists():
            record = read_json(receipt)
            if record["url"] != url or not path.exists() or sha256_file(path) != record["sha256"]:
                raise ValueError("Bronze download receipt does not match source bytes")
            return record
        if path.exists():
            raise ValueError(
                "Unmanifested bronze file exists; preserve and inspect before ingesting"
            )
        record = _download(url, path, config)
        write_json(receipt, record)
        return record

    # Per-file receipts let a failed second download resume without replacing
    # the successfully downloaded first source.
    trip = fetch(config.source.trip_url, trip_path)
    zones = fetch(config.source.zone_url, zone_path)
    try:
        schema = tlc_schema(trip_path)
        lookup = zone_lookup(zone_path)
    except ValueError as exc:
        write_json(
            bronze / "schema_failure.json", {"error": str(exc), "trip": trip, "zones": zones}
        )
        raise
    manifest = {
        "source_id": trip["sha256"],
        "source_kind": "observed_tlc",
        "source_complete": True,
        "source_version": TLC_SOURCE_VERSION,
        "trip": trip,
        "zones": zones,
        "schema": schema,
        "zone_rows": len(lookup),
        "assumed_timezone": config.source.assumed_timezone,
        "trip_path": str(trip_path.relative_to(config.workspace)).replace("\\", "/"),
        "zone_path": str(zone_path.relative_to(config.workspace)).replace("\\", "/"),
    }
    write_json(manifest_path, manifest)
    return manifest
