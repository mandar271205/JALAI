"""Versioned replay preparation. Outputs cannot mix with legacy rainfall_gfs."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from jalrakshak_ml.config import load_pilot_config, load_yaml
from jalrakshak_ml.preprocessing.grid import build_target_grid

from .core import (
    ALL_SUPPORTED_EVENTS,
    LOCKED_EVENTS,
    METHOD,
    NON_TEST_EVENTS,
    allocate_half_hours,
    finite_rain,
    reconstruct_hourly,
    select_gfs_forecast_as_of,
)
from .grib import fetch_field, read_field
from .schedule import materialize_schedule
from .spatial import reproject_rate


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_issue(
    root, event_id, selection, intervals, spatial, benchmark_sha256, *, reuse_verified=False
):
    """Atomically publish a complete per-issue NPZ + JSON record, never overwrite."""
    if event_id not in ALL_SUPPORTED_EVENTS:
        raise ValueError(f"Not a supported replay event: {event_id}")
    selection.validate()
    rates, windows = allocate_half_hours(intervals, selection)
    rates = rates.astype(np.float32)
    finite_rain(rates)
    grid = spatial["target_grid"]
    if rates.shape[1:] != tuple(grid["shape"]) or grid["crs"] != "EPSG:32643":
        raise ValueError("Canonical target grid mismatch")
    if event_id in LOCKED_EVENTS:
        split = "test"
        purpose = "held_out_replay_only"
    elif event_id == "mumbai_monsoon_2023_07_18":
        split = "train"
        purpose = "non_test_replay"
    elif event_id == "mumbai_monsoon_2023_07_25":
        split = "validation"
        purpose = "non_test_replay"
    else:
        split = "non_test"
        purpose = "non_test_replay"
    metadata = {
        "event_id": event_id,
        "split": split,
        "purpose": purpose,
        "issue_time": selection.issue_time.isoformat(),
        "cycle_time": selection.cycle_time.isoformat(),
        "availability_time": selection.availability_time.isoformat(),
        "availability_basis": selection.availability_basis,
        "forecast_age_hours": (selection.issue_time - selection.cycle_time).total_seconds() / 3600,
        "source_forecast_hours": list(selection.forecast_hours),
        "units": "mm/h",
        "internal_crs": "EPSG:32643",
        "api_crs": "EPSG:4326",
        "native_cadence_minutes": 60,
        "output_cadence_minutes": 30,
        "temporal_disaggregation_method": METHOD,
        "qc_flags": ["ASSUMED_AVAILABILITY"]
        if selection.availability_basis.startswith("assumed")
        else [],
        "spatial": spatial,
        "windows": windows,
        "benchmark_sha256": benchmark_sha256,
        "array_dimensions": ["output_horizon", "y", "x"],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    parent = Path(root) / event_id
    destination = parent / selection.issue_time.strftime("%Y%m%dT%H%MZ")
    if destination.exists():
        if reuse_verified:
            saved = json.loads((destination / "metadata.json").read_text(encoding="utf-8"))
            stable = lambda m: {
                k: v for k, v in m.items() if k not in ("generated_at", "array_sha256")
            }
            if (
                stable(saved) != stable(metadata)
                or sha256(destination / "rainfall.npz") != saved["array_sha256"]
            ):
                raise ValueError("Existing replay provenance/hash differs; use a new version")
            with np.load(destination / "rainfall.npz", allow_pickle=False) as arrays:
                np.testing.assert_array_equal(arrays["rainfall_rate_mm_h"], rates)
                np.testing.assert_array_equal(
                    arrays["native_rainfall_rate_mm_h"],
                    np.stack([w.rate for w in intervals]).astype(np.float32),
                )
                np.testing.assert_array_equal(
                    arrays["output_valid_time"], [w["output_valid_time"] for w in windows]
                )
            return destination, saved
        raise FileExistsError(f"Immutable replay issue already exists: {destination}")
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=parent) as staging_name:
        stage = Path(staging_name)
        np.savez_compressed(
            stage / "rainfall.npz",
            rainfall_rate_mm_h=rates,
            output_valid_time=np.array([w["output_valid_time"] for w in windows]),
            native_interval_start=np.array([w.start.isoformat() for w in intervals]),
            native_interval_end=np.array([w.end.isoformat() for w in intervals]),
            native_rainfall_rate_mm_h=np.stack([w.rate for w in intervals]).astype(np.float32),
            forecast_lead_hours=np.array([w["forecast_lead_hours"] for w in windows]),
        )
        metadata["array_sha256"] = sha256(stage / "rainfall.npz")
        (stage / "metadata.json").write_text(
            json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8"
        )
        # TemporaryDirectory only removes the now-absent staging path on exit.
        stage.rename(destination)
    return destination, metadata


def prepare(config_path, *, execute=False, download=False):
    config_path = Path(config_path).resolve()
    repo = config_path.parents[2]
    config = load_yaml(config_path)
    if (
        config["native_cadence_minutes"],
        config["output_cadence_minutes"],
        config["horizons_minutes"],
        config["temporal_disaggregation_method"],
    ) != (60, 30, [30, 60, 90, 120], METHOD):
        raise ValueError("Locked replay cadence changed")
    if config["purpose"] not in ("held_out_replay_only", "non_test_replay"):
        raise ValueError(f"Invalid replay purpose: {config['purpose']}")
    version = config["data_version"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", version):
        raise ValueError("Invalid data version")
    root = (repo / config["output_root"] / version).resolve()
    if not root.is_relative_to((repo / "data/processed/gfs_replay").resolve()):
        raise ValueError("Replay output must be separate from the legacy cube")
    schedule, schedule_path = materialize_schedule(config, repo)
    digest = sha256(schedule_path)
    planned = []
    for event in schedule["events"]:
        for sample in event["samples"]:
            selection = select_gfs_forecast_as_of(
                sample["issue_time"], 120, latency_hours=float(config["latency_hours"])
            )
            if [w.isoformat() for w in [selection.issue_time]] != [sample["input_times"][-1]]:
                raise ValueError("Benchmark issue mismatch")
            planned.append((event["event_id"], selection, sample))
    summary = {
        "data_version": version,
        "benchmark_sha256": digest,
        "benchmark_manifest": str(schedule_path),
        "sample_count": len(planned),
        "event_counts": {e["event_id"]: sum(x[0] == e["event_id"] for x in planned) for e in config["events"]},
        "status": "PLANNED",
        "latency_hours": config["latency_hours"],
        "FUSION_IMPLEMENTATION_STARTED": False,
    }
    if not execute:
        return summary
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        raise FileExistsError("Version already published; use its stored outputs or a new version")
    pilot = load_pilot_config(repo / config["pilot_config"])
    if pilot["api_crs"] != "EPSG:4326" or pilot["analysis_crs"] != "EPSG:32643":
        raise ValueError("Mumbai CRS contract changed")
    target = build_target_grid(
        bbox_wgs84=pilot["bbox_wgs84"],
        analysis_crs=pilot["analysis_crs"],
        width=pilot["grid"]["width"],
        height=pilot["grid"]["height"],
    )
    if (target["height"], target["width"]) != (256, 256):
        raise ValueError("Mumbai grid dimensions changed")
    cache = {}
    results = []
    for event_id, selection, sample in planned:
        fields = []
        for lead in selection.forecast_hours:
            key = (selection.cycle_time, lead)
            if key not in cache:
                print(f"Preparing {selection.cycle_time.isoformat()} f{lead:03d}", flush=True)
                path, requested, provenance = fetch_field(
                    selection.cycle_time,
                    lead,
                    repo / config["cache_dir"],
                    config["precipitation_product"],
                    allow_download=download,
                )
                values, lat, lon, meta = read_field(path, requested, pilot["bbox_wgs84"])
                # Keep high precision and reconstruct intervals before spatial resampling.
                cache[key] = (values, lat, lon, {**meta, **provenance})
            values, lat, lon, meta = cache[key]
            first = cache[(selection.cycle_time, 1)]
            if not np.array_equal(lat, first[1]) or not np.array_equal(lon, first[2]):
                raise ValueError("Source grid changed between cumulative fields")
            fields.append((values, meta))
        native = reconstruct_hourly(fields)
        projected = []
        for interval in native:
            rate, spatial = reproject_rate(interval.rate, lat, lon, target)
            projected.append(replace(interval, rate=rate))
        _, windows = allocate_half_hours(projected, selection)
        if [w["output_valid_time"] for w in windows] != sample["target_times"]:
            raise ValueError("Replay times differ from locked benchmark targets")
        destination, metadata = save_issue(
            root, event_id, selection, projected, spatial, digest, reuse_verified=True
        )
        results.append(
            {
                "event_id": event_id,
                "issue_time": selection.issue_time.isoformat(),
                "path": destination.relative_to(root).as_posix(),
                "array_sha256": metadata["array_sha256"],
            }
        )
        print(
            f"Published {len(results)}/{len(planned)} {event_id} {sample['issue_time']}", flush=True
        )
    summary.update(
        {
            "status": "COMPLETED",
            "samples": results,
            "availability_verified": False,
            "availability_note": "Six-hour conservative policy; not observed release times",
            "config": config,
        }
    )
    root.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
    return summary
