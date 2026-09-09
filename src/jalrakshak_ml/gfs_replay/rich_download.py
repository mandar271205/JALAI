"""Resumable byte-range acquisition for Phase 4E rich GFS source messages."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import requests

from jalrakshak_ml.deep_nowcast.splits import is_locked_test_event

from .core import source_uri, utc
from .grib import read_field, rich_index_ranges, selector

REQUIRED_FIELDS = ("u10", "v10", "t2m", "rh2m", "sp", "cape", "pwat", "prate_mean")
AVAILABILITY_BASIS = "assumed_cycle_plus_6h_required_bundle_not_observed_publication"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_grib_envelope(path: str | Path, expected_size: int | None = None) -> int:
    path = Path(path)
    size = path.stat().st_size
    if expected_size is not None and size != expected_size:
        raise ValueError(f"GRIB size mismatch: expected {expected_size}, found {size}")
    if size < 16:
        raise ValueError("GRIB message is too small")
    with path.open("rb") as stream:
        head = stream.read(16)
        stream.seek(-4, os.SEEK_END)
        tail = stream.read(4)
    if head[:4] != b"GRIB" or tail != b"7777" or int.from_bytes(head[8:16], "big") != size:
        raise ValueError("Invalid or incomplete GRIB message envelope")
    return size


def parse_prate_interval(metadata: dict[str, Any]) -> dict[str, Any]:
    """Formalize interval-average PRATE timing without inventing half-hour data."""
    required = (
        "shortName",
        "typeOfLevel",
        "level",
        "stepType",
        "startStep",
        "endStep",
        "units",
        "forecast_reference_time",
        "valid_time",
    )
    missing = [key for key in required if key not in metadata]
    if missing:
        raise ValueError(f"PRATE metadata missing: {missing}")
    if (
        metadata["shortName"],
        metadata["typeOfLevel"],
        int(metadata["level"]),
        metadata["stepType"],
    ) != ("prate", "surface", 0, "avg"):
        raise ValueError("Expected exact interval-mean surface PRATE")
    start, end = float(metadata["startStep"]), float(metadata["endStep"])
    if start < 0 or end <= start or not start.is_integer() or not end.is_integer():
        raise ValueError("Invalid PRATE interval steps")
    cycle = utc(metadata["forecast_reference_time"])
    valid = utc(metadata["valid_time"])
    if valid != cycle + timedelta(hours=end):
        raise ValueError("PRATE valid time differs from cycle plus end step")
    units = str(metadata["units"]).replace(" ", "")
    if units not in ("kgm**-2s**-1", "kgm^-2s^-1", "kg/m^2/s"):
        raise ValueError(f"Unsupported PRATE units: {metadata['units']}")
    return {
        "cycle_time": cycle.isoformat(),
        "forecast_lead": int(end),
        "start_step": int(start),
        "end_step": int(end),
        "step_type": "avg",
        "source_interval_start": (cycle + timedelta(hours=start)).isoformat(),
        "source_interval_end": (cycle + timedelta(hours=end)).isoformat(),
        "native_valid_time": valid.isoformat(),
        "units": metadata["units"],
        "native_cadence_minutes": int((end - start) * 60),
    }


def default_message_validator(
    path: Path, variable: str, cycle: datetime, lead: int
) -> dict[str, Any]:
    bbox = (72.70, 18.80, 73.10, 19.35)
    if variable == "prate_mean":
        values, _, _, metadata = read_field(path, selector("prate_mean", cycle, lead), bbox)
        if not np.isfinite(values).all() or np.any(values < 0):
            raise ValueError("Invalid PRATE values")
        return {
            "grib_parse_state": "PASSED",
            "source_valid_time": metadata["valid_time"],
            "precip_interval_metadata": parse_prate_interval(metadata),
            "grib_metadata": metadata,
            "finite_percentage": 100.0,
            "physical_min": float(values.min()),
            "physical_max": float(values.max()),
        }
    from jalrakshak_ml.weather.adapters.gfs_rich import read_exact_gfs_field

    values, _, _, metadata = read_exact_gfs_field(path, variable, bbox=bbox)
    if not np.isfinite(values).all():
        raise ValueError(f"Non-finite {variable} values")
    expected = utc(cycle) + timedelta(hours=lead)
    if utc(metadata["valid_time"]) != expected:
        raise ValueError(f"{variable} valid time mismatch")
    return {
        "grib_parse_state": "PASSED",
        "source_valid_time": expected.isoformat(),
        "precip_interval_metadata": None,
        "grib_metadata": metadata,
        "finite_percentage": 100.0,
        "physical_min": float(values.min()),
        "physical_max": float(values.max()),
    }


def granule_directory(cache_root: str | Path, cycle: str | datetime, lead: int) -> Path:
    return Path(cache_root) / f"{utc(cycle):%Y%m%d_%H}" / f"f{lead:03d}"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    part.replace(path)


def _get_with_retry(
    http,
    url: str,
    *,
    headers=None,
    stream=False,
    attempts=4,
    connection_timeout=10.0,
    read_timeout=60.0,
    sleep: Callable[[float], None] = time.sleep,
):
    last_error = None
    for retry in range(attempts):
        try:
            response = http.get(
                url, headers=headers, stream=stream, timeout=(connection_timeout, read_timeout)
            )
            if response.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"retryable HTTP {response.status_code}")
            response.raise_for_status()
            return response, retry
        except (requests.RequestException, OSError) as error:
            last_error = error
            if retry + 1 == attempts:
                break
            sleep(min(8.0, 0.5 * (2**retry)))
    raise RuntimeError(f"Bounded download failed after {attempts} attempts") from last_error


def acquire_rich_granule(
    cycle: str | datetime,
    lead: int,
    cache_root: str | Path,
    *,
    session=None,
    validator: Callable[[Path, str, datetime, int], dict[str, Any]] = default_message_validator,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Acquire one complete eight-field granule; safely resumes validated fields."""
    cycle = utc(cycle)
    uri = source_uri(cycle, lead)
    directory = granule_directory(cache_root, cycle, lead)
    manifest_path = directory / "manifest.json"
    directory.mkdir(parents=True, exist_ok=True)
    previous = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    )
    manifest = {
        "manifest_version": "phase4e_rich_gfs_raw_v1",
        "cycle": cycle.isoformat(),
        "lead": lead,
        "source_url": uri,
        "idx_url": uri + ".idx",
        "variables_expected": list(REQUIRED_FIELDS),
        "variables": previous.get("variables", {}),
        "completion_state": "INCOMPLETE",
        "full_grib_fallback": False,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    http = session or requests.Session()
    response, idx_retries = _get_with_retry(http, uri + ".idx", sleep=sleep)
    idx_http_status = response.status_code
    idx_text = response.text
    ranges = rich_index_ranges(idx_text, REQUIRED_FIELDS, lead)
    failures = []
    for variable in REQUIRED_FIELDS:
        begin, end = ranges[variable]
        expected_size = end - begin + 1
        path = directory / f"{variable}.grib2"
        record = manifest["variables"].get(variable, {})
        try:
            reused = False
            if path.exists() and record.get("completion_state") == "COMPLETE":
                validate_grib_envelope(path, expected_size)
                if sha256_file(path) != record.get("sha256"):
                    raise ValueError("Cached SHA256 mismatch")
                parsed = validator(path, variable, cycle, lead)
                reused = True
                retries = 0
                http_status = record.get("http_status", 206)
            else:
                part = path.with_suffix(".grib2.part")
                if part.exists():
                    part.unlink()
                response, retries = _get_with_retry(
                    http, uri, headers={"Range": f"bytes={begin}-{end}"}, stream=True, sleep=sleep
                )
                expected_header = rf"bytes {begin}-{end}/\d+"
                if response.status_code != 206 or not re.fullmatch(
                    expected_header, response.headers.get("Content-Range", "")
                ):
                    raise ValueError("Range request was not honored; full-GRIB fallback forbidden")
                data = response.raw.read(expected_size + 1)
                if len(data) != expected_size:
                    raise ValueError("Partial or oversized byte-range response")
                with part.open("xb") as stream:
                    stream.write(data)
                validate_grib_envelope(part, expected_size)
                parsed = validator(part, variable, cycle, lead)
                part.replace(path)
                http_status = response.status_code
            manifest["variables"][variable] = {
                "completion_state": "COMPLETE",
                "path": path.name,
                "byte_range": [begin, end],
                "bytes_received": path.stat().st_size,
                "sha256": sha256_file(path),
                "http_status": http_status,
                "grib_parse_state": parsed["grib_parse_state"],
                "source_valid_time": parsed["source_valid_time"],
                "precip_interval_metadata": parsed["precip_interval_metadata"],
                "finite_percentage": parsed["finite_percentage"],
                "physical_min": parsed["physical_min"],
                "physical_max": parsed["physical_max"],
                "download_timestamp": record.get("download_timestamp")
                if reused
                else datetime.now(UTC).isoformat(),
                "retry_count": retries,
                "resumed_from_valid_cache": reused,
            }
        except Exception as error:  # noqa: BLE001 - every acquisition failure is recorded atomically
            (directory / f"{variable}.grib2.part").unlink(missing_ok=True)
            manifest["variables"][variable] = {
                **record,
                "completion_state": "FAILED",
                "byte_range": [begin, end],
                "bytes_received": path.stat().st_size if path.exists() else 0,
                "grib_parse_state": "FAILED",
                "error": f"{type(error).__name__}: {error}",
            }
            failures.append(variable)
        finally:
            manifest["updated_at"] = datetime.now(UTC).isoformat()
            _atomic_json(manifest_path, manifest)
    complete = all(
        manifest["variables"].get(key, {}).get("completion_state") == "COMPLETE"
        for key in REQUIRED_FIELDS
    )
    manifest.update(
        {
            "idx_http_status": idx_http_status,
            "idx_retry_count": idx_retries,
            "variables_downloaded": [
                key
                for key in REQUIRED_FIELDS
                if manifest["variables"].get(key, {}).get("completion_state") == "COMPLETE"
            ],
            "completion_state": "COMPLETE" if complete else "INCOMPLETE",
            "total_measured_bytes": sum(
                int(item.get("bytes_received", 0)) for item in manifest["variables"].values()
            ),
            "failed_variables": failures,
        }
    )
    _atomic_json(manifest_path, manifest)
    return manifest


def initialize_download_manifest(plan: dict[str, Any], cache_root: str | Path) -> dict[str, Any]:
    pairs = plan["unique_cycle_leads_required"]
    if plan["num_unique_cycle_leads"] != 225 or len(pairs) != 225:
        raise ValueError("Phase 4E raw plan must contain exactly 225 pairs")
    if any(is_locked_test_event(event_id) for event_id in plan["events"]):
        raise PermissionError("Locked-test event found in non-test download plan")
    manifest_pairs = [
        {
            "cycle": item["cycle"],
            "lead": item["lead"],
            "source_url": source_uri(item["cycle"], item["lead"]),
            "idx_url": source_uri(item["cycle"], item["lead"]) + ".idx",
            "variables_expected": list(REQUIRED_FIELDS),
            "completion_state": "MISSING",
        }
        for item in pairs
    ]
    return {
        "manifest_version": "phase4e_rich_gfs_download_v1",
        "cache_root": str(cache_root),
        "expected_pairs": 225,
        "completed_pairs": 0,
        "incomplete_pairs": 0,
        "missing_pairs": 225,
        "failed_pairs": 0,
        "total_measured_bytes": 0,
        "required_fields": list(REQUIRED_FIELDS),
        "pairs": manifest_pairs,
        "execution_state": "NOT_STARTED",
        "full_grib_fallback": False,
    }
