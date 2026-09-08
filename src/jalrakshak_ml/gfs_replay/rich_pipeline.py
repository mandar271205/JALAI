"""Phase 4E Rich GFS Replay Pipeline for JalRakshak AI (SIH26071).

Constructs immutable, versioned, multi-variable GFS replay archives for
the 15 non-test training and validation events.

Stores:
- rainfall.npz: precipitation rate (mm/h) across 4 horizons (+30, +60, +90, +120m)
- meteorology.npz:
    - gfs_u10 (m/s)
    - gfs_v10 (m/s)
    - gfs_wind_speed (m/s)
    - gfs_wind_direction_sin (dimensionless, [-1, 1])
    - gfs_wind_direction_cos (dimensionless, [-1, 1])
    - gfs_t2m (K)
    - gfs_rh2m (%)
    - gfs_surface_pressure (Pa)
    - gfs_cape (J/kg)
    - gfs_pwat (kg/m^2)
- metadata.json: provenance, exact GRIB identities, hashes, timestamps, QC flags.

CRITICAL NON-LEAKAGE RULE:
This module operates ONLY on the 15 train and validation events.
Locked test events are strictly prohibited from this pipeline.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from jalrakshak_ml.deep_nowcast.splits import (
    LOCKED_TEST_EVENTS_AUTHORITATIVE,
    TRAIN_EVENTS_AUTHORITATIVE,
    VALIDATION_EVENTS_AUTHORITATIVE,
    is_locked_test_event,
)
from jalrakshak_ml.gfs_replay.core import (
    Selection,
    allocate_half_hours,
    finite_rain,
    select_gfs_forecast_as_of,
    utc,
)
from jalrakshak_ml.gfs_replay.spatial import canonicalize_grid, reproject_rate
from jalrakshak_ml.weather.adapters.gfs_rich import (
    GFS_VARIABLE_SPECS,
    derive_wind_speed_and_direction,
)

log = logging.getLogger(__name__)

RICH_GFS_REPLAY_VERSION = "gfs_mumbai_phase4e_rich_non_test_v1"

RICH_VARIABLE_KEYS = (
    "u10",
    "v10",
    "t2m",
    "rh2m",
    "sp",
    "cape",
    "pwat",
)

METEOROLOGY_ARRAY_KEYS = (
    "gfs_u10",
    "gfs_v10",
    "gfs_wind_speed",
    "gfs_wind_direction_sin",
    "gfs_wind_direction_cos",
    "gfs_t2m",
    "gfs_rh2m",
    "gfs_surface_pressure",
    "gfs_cape",
    "gfs_pwat",
)


def compute_sha256(file_path: Path | str) -> str:
    """Compute SHA-256 hash of a file."""
    return hashlib.sha256(Path(file_path).read_bytes()).hexdigest()


def derive_cyclic_wind_direction(
    u: np.ndarray, v: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute wind speed and cyclic (sin, cos) components of meteorological wind direction.

    Meteorological direction (from which wind blows):
    deg = (270.0 - rad2deg(atan2(v, u))) % 360.0
    theta_rad = radians(deg)
    sin_dir = sin(theta_rad)
    cos_dir = cos(theta_rad)
    """
    speed, deg, _ = derive_wind_speed_and_direction(u, v)
    theta_rad = np.radians(deg)
    sin_dir = np.sin(theta_rad).astype(np.float32)
    cos_dir = np.cos(theta_rad).astype(np.float32)
    return speed.astype(np.float32), sin_dir, cos_dir


@dataclass(slots=True)
class RichIssuePayload:
    """Multi-variable payload for a single issue forecast (4 horizons)."""

    event_id: str
    issue_time: datetime
    selection: Selection
    rainfall_rate: np.ndarray          # shape (4, H, W)
    meteorology_fields: dict[str, np.ndarray]  # key -> shape (4, H, W)
    spatial_metadata: dict[str, Any]

    def validate(self) -> None:
        if is_locked_test_event(self.event_id):
            raise PermissionError(
                f"LOCKED TEST EVENT {self.event_id} CANNOT BE INCLUDED IN NON-TEST RICH REPLAY!"
            )
        if self.rainfall_rate.shape[0] != 4:
            raise ValueError(f"Rainfall must have 4 horizons, got {self.rainfall_rate.shape}")
        finite_rain(self.rainfall_rate)
        for key in METEOROLOGY_ARRAY_KEYS:
            if key not in self.meteorology_fields:
                raise ValueError(f"Missing required meteorological array: {key}")
            arr = self.meteorology_fields[key]
            if arr.shape != self.rainfall_rate.shape:
                raise ValueError(
                    f"Shape mismatch for {key}: expected {self.rainfall_rate.shape}, got {arr.shape}"
                )
            if not np.all(np.isfinite(arr)):
                raise ValueError(f"Array {key} contains non-finite values (NaN/Inf)")


def save_rich_issue(
    output_root: Path | str,
    payload: RichIssuePayload,
    *,
    reuse_verified: bool = True,
) -> Path:
    """Atomically write rainfall.npz, meteorology.npz, and metadata.json for an issue time.

    Enforces immutable write semantics: fails if existing files have mismatched content.
    """
    payload.validate()
    event_id = payload.event_id
    issue_time = payload.issue_time
    selection = payload.selection

    if event_id in TRAIN_EVENTS_AUTHORITATIVE:
        split = "train"
    elif event_id in VALIDATION_EVENTS_AUTHORITATIVE:
        split = "validation"
    else:
        raise ValueError(f"Event {event_id} is not an authorized non-test event")

    time_key = issue_time.strftime("%Y%m%dT%H%MZ")
    dest_dir = Path(output_root) / event_id / time_key
    dest_dir.mkdir(parents=True, exist_ok=True)

    rainfall_path = dest_dir / "rainfall.npz"
    meteo_path = dest_dir / "meteorology.npz"
    metadata_path = dest_dir / "metadata.json"

    # Temporary files for atomic write
    tmp_rainfall = dest_dir / "rainfall.tmp.npz"
    tmp_meteo = dest_dir / "meteorology.tmp.npz"
    tmp_meta = dest_dir / "metadata.tmp.json"

    # 1. Save rainfall.npz
    np.savez_compressed(
        tmp_rainfall,
        rainfall_rate_mm_h=payload.rainfall_rate.astype(np.float32),
    )
    rain_hash = compute_sha256(tmp_rainfall)

    # 2. Save meteorology.npz
    np.savez_compressed(
        tmp_meteo,
        **{k: payload.meteorology_fields[k].astype(np.float32) for k in METEOROLOGY_ARRAY_KEYS},
    )
    meteo_hash = compute_sha256(tmp_meteo)

    # 3. Construct metadata
    metadata = {
        "replay_version": RICH_GFS_REPLAY_VERSION,
        "event_id": event_id,
        "split": split,
        "purpose": "phase4e_rich_multisource_non_test_replay",
        "issue_time": issue_time.isoformat(),
        "cycle_time": selection.cycle_time.isoformat(),
        "availability_time": selection.availability_time.isoformat(),
        "availability_basis": selection.availability_basis,
        "forecast_age_hours": (issue_time - selection.cycle_time).total_seconds() / 3600.0,
        "source_forecast_hours": list(selection.forecast_hours),
        "temporal_alignment_policy": "step_forward_nearest_causal",
        "native_cadence_minutes": 60,
        "output_cadence_minutes": 30,
        "native_resolution": "0.25_deg (~28 km)",
        "canonical_resolution": "256x256 (EPSG:32643)",
        "scientific_disclaimer": (
            "Reprojection to the canonical 256x256 target grid is for spatial tensor alignment "
            "and does NOT increase meteorological resolution or information beyond native 0.25-deg GFS."
        ),
        "qc_flags": ["ASSUMED_AVAILABILITY"]
        if selection.availability_basis.startswith("assumed")
        else [],
        "units": {
            "rainfall_rate_mm_h": "mm/h",
            "gfs_u10": "m/s",
            "gfs_v10": "m/s",
            "gfs_wind_speed": "m/s",
            "gfs_wind_direction_sin": "dimensionless",
            "gfs_wind_direction_cos": "dimensionless",
            "gfs_t2m": "K",
            "gfs_rh2m": "%",
            "gfs_surface_pressure": "Pa",
            "gfs_cape": "J/kg",
            "gfs_pwat": "kg/m^2",
        },
        "array_dimensions": ["output_horizon", "y", "x"],
        "horizons_minutes": [30, 60, 90, 120],
        "rainfall_sha256": rain_hash,
        "meteorology_sha256": meteo_hash,
        "spatial": payload.spatial_metadata,
        "generated_at": datetime.now(UTC).isoformat(),
    }

    if rainfall_path.exists() and meteo_path.exists() and metadata_path.exists():
        if reuse_verified:
            existing_rain_hash = compute_sha256(rainfall_path)
            existing_meteo_hash = compute_sha256(meteo_path)
            if existing_rain_hash == rain_hash and existing_meteo_hash == meteo_hash:
                tmp_rainfall.unlink(missing_ok=True)
                tmp_meteo.unlink(missing_ok=True)
                tmp_meta.unlink(missing_ok=True)
                return dest_dir
            raise ValueError(
                f"Existing replay at {dest_dir} has conflicting hashes! "
                f"Immutable replay rules forbid overwriting."
            )
        raise FileExistsError(f"Replay directory already exists: {dest_dir}")

    # Atomic move
    tmp_rainfall.replace(rainfall_path)
    tmp_meteo.replace(meteo_path)
    tmp_meta.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    tmp_meta.replace(metadata_path)

    return dest_dir


def plan_rich_replay_for_events(
    events: list[dict[str, Any]],
    assumed_latency_hours: float = 6.0,
) -> dict[str, Any]:
    """Calculate the required GFS cycles, timestamps, and steps for events without downloading."""
    plan: dict[str, Any] = {
        "replay_version": RICH_GFS_REPLAY_VERSION,
        "planned_at": datetime.now(UTC).isoformat(),
        "total_events": len(events),
        "events": {},
        "unique_cycles_required": set(),
        "total_issues": 0,
    }

    for ev in events:
        event_id = ev["event_id"]
        if is_locked_test_event(event_id):
            raise PermissionError(f"Locked test event {event_id} cannot be planned in non-test replay.")
        start = utc(ev["start_time"])
        end = utc(ev["end_time"])

        event_plan: list[dict[str, Any]] = []
        current = start + timedelta(hours=2.0)  # first issue time after 2h history
        while current <= end:
            sel = select_gfs_forecast_as_of(current, 120, latency_hours=assumed_latency_hours)
            cycle_str = sel.cycle_time.strftime("%Y%m%d_%H%M")
            plan["unique_cycles_required"].add(cycle_str)
            event_plan.append({
                "issue_time": current.isoformat(),
                "cycle_time": sel.cycle_time.isoformat(),
                "forecast_hours": list(sel.forecast_hours),
                "forecast_age_hours": (current - sel.cycle_time).total_seconds() / 3600.0,
            })
            current += timedelta(minutes=30)

        plan["events"][event_id] = {
            "split": ev.get("research_split", "train"),
            "issues": event_plan,
            "num_issues": len(event_plan),
        }
        plan["total_issues"] += len(event_plan)

    plan["unique_cycles_required"] = sorted(plan["unique_cycles_required"])
    plan["num_unique_cycles"] = len(plan["unique_cycles_required"])
    return plan
