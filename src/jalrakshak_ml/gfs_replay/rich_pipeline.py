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
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from jalrakshak_ml.deep_nowcast.splits import (
    TRAIN_EVENTS_AUTHORITATIVE,
    VALIDATION_EVENTS_AUTHORITATIVE,
    build_event_sequences,
    is_locked_test_event,
)
from jalrakshak_ml.gfs_replay.core import (
    Selection,
    finite_rain,
    prate_mean_to_rate,
    reconstruct_hourly,  # kept for APCP backward compatibility
    select_gfs_forecast_as_of,
    utc,
)
from jalrakshak_ml.gfs_replay.grib import read_field, selector
from jalrakshak_ml.gfs_replay.rich_download import (
    AVAILABILITY_BASIS,
    granule_directory,
    parse_prate_interval,
    sha256_file,
)
from jalrakshak_ml.gfs_replay.spatial import reproject_field, reproject_rate
from jalrakshak_ml.weather.adapters.gfs_rich import (
    GFS_VARIABLE_SPECS,
    derive_wind_speed_and_direction,
    read_exact_gfs_field,
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


def resolve_rich_gfs_output_dir(override: Path | str | None = None) -> Path:
    """Resolve destination directory for Phase 4E rich GFS replay.

    Priority:
    1. Explicit override argument (e.g. from CLI --output-dir)
    2. JALAI_RICH_GFS_DIR environment variable
    3. Default repo path: data/processed/gfs_replay/gfs_mumbai_phase4e_rich_non_test_v1
    """
    if override is not None and str(override).strip():
        resolved = Path(override)
    elif "JALAI_RICH_GFS_DIR" in os.environ and os.environ["JALAI_RICH_GFS_DIR"].strip():
        resolved = Path(os.environ["JALAI_RICH_GFS_DIR"])
    else:
        resolved = Path("data/processed/gfs_replay") / RICH_GFS_REPLAY_VERSION
    return resolved


def check_colab_drive_persistence(output_dir: Path | str) -> list[str]:
    """Emit warnings/guards when running in Google Colab without Google Drive persistence."""
    import warnings as py_warnings

    warnings_list = []
    out_str = str(output_dir).replace("\\", "/")
    is_colab = "google.colab" in sys.modules and Path("/content").is_dir()
    colab_style_path = out_str.startswith("/content/")

    if (is_colab or colab_style_path) and "/content/drive" not in out_str:
        warning_msg = (
            f"COLAB EPHEMERAL STORAGE WARNING: Resolved output path {out_str} is located in ephemeral "
            f"container storage (/content/...). Data will be lost upon runtime disconnect! "
            f"Recommended Colab persistent destination: "
            f"/content/drive/MyDrive/JALAI_DATA/processed/gfs_replay/{RICH_GFS_REPLAY_VERSION}"
        )
        log.warning(warning_msg)
        py_warnings.warn(warning_msg, UserWarning, stacklevel=2)
        warnings_list.append(warning_msg)
    return warnings_list


def persistence_environment(output_dir: Path | str) -> dict[str, bool]:
    """Distinguish local persistence from a genuine mounted Colab Drive."""
    output = Path(output_dir)
    is_colab = "google.colab" in sys.modules and Path("/content").is_dir()
    drive_root = Path("/content/drive/MyDrive")
    try:
        under_drive = output.resolve().is_relative_to(drive_root.resolve())
    except (OSError, RuntimeError):
        under_drive = False
    return {
        "NETWORK_SMOKE_VERIFIED": False,
        "LOCAL_PERSISTENCE_VERIFIED": False,
        "COLAB_DRIVE_PERSISTENCE_VERIFIED": bool(is_colab and drive_root.is_dir() and under_drive),
    }


@dataclass(slots=True)
class RichIssuePayload:
    """Multi-variable payload for a single issue forecast (4 horizons)."""

    event_id: str
    issue_time: datetime
    selection: Selection
    rainfall_rate: np.ndarray  # shape (4, H, W)
    meteorology_fields: dict[str, np.ndarray]  # key -> shape (4, H, W)
    spatial_metadata: dict[str, Any]
    source_provenance: dict[str, Any] | None = None
    temporal_metadata: dict[str, Any] | None = None
    availability_masks: dict[str, np.ndarray] | None = None

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
        if self.source_provenance is not None:
            for key in ("gfs_precipitation", *METEOROLOGY_ARRAY_KEYS):
                if key not in self.source_provenance:
                    raise ValueError(f"Missing source provenance for {key}")


def save_rich_issue(
    output_root: Path | str | None,
    payload: RichIssuePayload,
    *,
    reuse_verified: bool = True,
) -> Path:
    """Atomically write rainfall.npz, meteorology.npz, and metadata.json for an issue time.

    Enforces immutable write semantics: fails if existing files have mismatched content.
    """
    payload.validate()
    resolved_root = resolve_rich_gfs_output_dir(output_root)
    check_colab_drive_persistence(resolved_root)

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
    dest_dir = resolved_root / event_id / time_key
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
        "availability_basis": AVAILABILITY_BASIS
        if selection.availability_basis.startswith("assumed")
        else selection.availability_basis,
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
        "source_provenance": payload.source_provenance,
        "temporal_metadata": payload.temporal_metadata,
        "availability_masks": {
            key: np.asarray(value, dtype=bool).tolist()
            for key, value in (payload.availability_masks or {}).items()
        },
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


def select_rich_gfs_leads_for_issue(
    issue_time: datetime | str,
    cycle_time: datetime | str,
    target_times: Sequence[datetime | str],
) -> tuple[int, ...]:
    """Select the minimal set of native GFS forecast leads for an issue time.

    Conditioning horizons: +30, +60, +90, +120 minutes.
    - Instantaneous fields: latest native hourly forecast valid time <= requested conditioning valid time
      lead = floor((T_valid - cycle_time) / 3600).
    - Precipitation fields: native hourly intervals covering each 30-min window [T_valid - 30m, T_valid]
      end_lead = ceil((T_valid - cycle_time) / 3600),
      start_lead = floor((T_valid - 30m - cycle_time) / 3600).

    Deduplicates at (cycle_time, forecast_lead) and returns sorted tuple of minimal integer forecast leads.
    """
    cycle_dt = utc(cycle_time)
    leads: set[int] = set()

    for t in target_times:
        t_dt = utc(t)
        # 1. Instantaneous step-forward nearest causal lead:
        inst_lead = int((t_dt - cycle_dt).total_seconds() // 3600)
        if inst_lead > 0:
            leads.add(inst_lead)

        # 2. Precipitation interval coverage:
        end_step = math.ceil((t_dt - cycle_dt).total_seconds() / 3600)
        if end_step > 0:
            leads.add(end_step)
        start_step = math.floor((t_dt - timedelta(minutes=30) - cycle_dt).total_seconds() / 3600)
        if start_step > 0:
            leads.add(start_step)

    return tuple(sorted(leads))


class AlignmentRecord(dict):
    """Record describing instantaneous causal alignment for an output horizon."""

    def __init__(
        self,
        horizon_minutes: int,
        target_valid_time: datetime,
        native_gfs_cycle: datetime,
        selected_lead_hour: int,
        source_valid_time: datetime,
        age_minutes: int,
        alignment_method: str = "step_forward_nearest_causal",
        availability_time: datetime | None = None,
        availability_basis: str = AVAILABILITY_BASIS,
    ):
        available = availability_time or native_gfs_cycle + timedelta(hours=6)
        super().__init__(
            {
                "horizon_minutes": horizon_minutes,
                "conditioning_valid_time": target_valid_time.isoformat(),
                "target_valid_time": target_valid_time.isoformat(),
                "native_gfs_cycle": native_gfs_cycle.isoformat(),
                "native_gfs_lead": selected_lead_hour,
                "selected_lead_hour": selected_lead_hour,
                "native_gfs_valid_time": source_valid_time.isoformat(),
                "source_valid_time": source_valid_time.isoformat(),
                "temporal_offset_minutes": age_minutes,
                "age_minutes": age_minutes,
                "aligned_target_time": target_valid_time.isoformat(),
                "source_native_valid_time": source_valid_time.isoformat(),
                "source_age_minutes": age_minutes,
                "cycle_time": native_gfs_cycle.isoformat(),
                "lead_hour": selected_lead_hour,
                "availability_time": available.isoformat(),
                "availability_basis": availability_basis,
                "alignment_method": alignment_method,
            }
        )
        self.horizon_minutes = horizon_minutes
        self.target_valid_time = target_valid_time
        self.source_valid_time = source_valid_time
        self.native_gfs_cycle = native_gfs_cycle
        self.selected_lead_hour = selected_lead_hour
        self.age_minutes = age_minutes
        self.alignment_method = alignment_method


def align_instantaneous_horizons(
    arg1: datetime | str,
    arg2: datetime | str,
    horizons_minutes: tuple[int, ...] = (30, 60, 90, 120),
) -> list[AlignmentRecord]:
    """Determine the exact causal temporal alignment for instantaneous meteorological fields.

    Policy: step-forward nearest causal:
    latest native forecast valid time <= requested conditioning valid time.
    Never uses a future native forecast step relative to requested conditioning valid time.
    """
    dt1 = utc(arg1)
    dt2 = utc(arg2)
    # Be flexible with argument order (issue_time, cycle_time) vs (cycle_time, issue_time)
    if dt1 > dt2:
        issue_dt = dt1
        cycle_dt = dt2
    else:
        cycle_dt = dt1
        issue_dt = dt2

    alignments = []

    for h_mins in horizons_minutes:
        target_dt = issue_dt + timedelta(minutes=h_mins)
        native_lead = int((target_dt - cycle_dt).total_seconds() // 3600)
        native_valid_dt = cycle_dt + timedelta(hours=native_lead)

        if native_valid_dt > target_dt:
            raise ValueError(
                f"Future forecast leakage detected: native valid {native_valid_dt.isoformat()} > "
                f"conditioning target {target_dt.isoformat()}"
            )

        offset_mins = int((target_dt - native_valid_dt).total_seconds() // 60)
        alignments.append(
            AlignmentRecord(
                horizon_minutes=h_mins,
                target_valid_time=target_dt,
                native_gfs_cycle=cycle_dt,
                selected_lead_hour=native_lead,
                source_valid_time=native_valid_dt,
                age_minutes=offset_mins,
                alignment_method="step_forward_nearest_causal",
            )
        )

    return alignments


def align_prate_horizons(
    issue_time: datetime | str,
    cycle_time: datetime | str,
    metadata_by_end_step: dict[int, dict[str, Any]],
    horizons_minutes: tuple[int, ...] = (30, 60, 90, 120),
) -> list[dict[str, Any]]:
    """Map half-hour slots to native hourly PRATE intervals, preserving provenance."""
    issue, cycle = utc(issue_time), utc(cycle_time)
    output = []
    for horizon in horizons_minutes:
        aligned = issue + timedelta(minutes=horizon)
        lead = math.ceil((aligned - cycle).total_seconds() / 3600)
        if lead not in metadata_by_end_step:
            raise ValueError(f"Missing native PRATE interval ending at lead {lead}")
        native = parse_prate_interval(metadata_by_end_step[lead])
        slot_start = aligned - timedelta(minutes=30)
        source_start = cycle + timedelta(hours=lead - 1)
        source_end = cycle + timedelta(hours=lead)
        if not source_start <= slot_start < aligned <= source_end:
            raise ValueError("Half-hour slot is not covered by native PRATE interval")
        output.append(
            {
                "horizon_minutes": horizon,
                "aligned_target_time": aligned.isoformat(),
                "source_native_valid_time": native["native_valid_time"],
                "source_interval_start": native["source_interval_start"],
                "source_interval_end": native["source_interval_end"],
                "reconstructed_native_interval_start": source_start.isoformat(),
                "reconstructed_native_interval_end": source_end.isoformat(),
                "raw_prate_statistical_interval": native,
                "source_age_minutes": int((aligned - source_end).total_seconds() / 60),
                "cycle_time": cycle.isoformat(),
                "lead_hour": lead,
                "availability_time": (cycle + timedelta(hours=6)).isoformat(),
                "availability_basis": AVAILABILITY_BASIS,
                "native_cadence_minutes": 60,
                "output_cadence_minutes": 30,
                "temporal_disaggregation_method": "uniform_within_native_interval",
                "independent_native_observation": False,
            }
        )
    return output


def build_rich_issue_from_cache(
    event_id: str,
    issue_time: datetime | str,
    target_times: Sequence[datetime | str],
    cache_root: str | Path,
    target_grid: dict[str, Any],
) -> RichIssuePayload:
    """Build one rich issue strictly from a complete raw cache; performs no downloads."""
    if is_locked_test_event(event_id):
        raise PermissionError(f"Locked-test event is forbidden: {event_id}")
    issue = utc(issue_time)
    selection = select_gfs_forecast_as_of(issue, 120, latency_hours=6)
    targets = [utc(value) for value in target_times]
    if targets != [issue + timedelta(minutes=value) for value in (30, 60, 90, 120)]:
        raise ValueError("Target times must be the four locked half-hour horizons")
    instant_alignment = align_instantaneous_horizons(issue, selection.cycle_time)
    raw_fields = {key: [] for key in RICH_VARIABLE_KEYS}
    source_provenance: dict[str, Any] = {}
    meteorology = {key: [] for key in METEOROLOGY_ARRAY_KEYS}
    for alignment in instant_alignment:
        lead = alignment.selected_lead_hour
        directory = granule_directory(cache_root, selection.cycle_time, lead)
        projected = {}
        for variable in RICH_VARIABLE_KEYS:
            path = directory / f"{variable}.grib2"
            values, lat, lon, metadata = read_exact_gfs_field(path, variable)
            values, spatial = reproject_field(
                values,
                lat,
                lon,
                target_grid,
                variable_name=variable,
                physical_range=GFS_VARIABLE_SPECS[variable]["physical_range"],
            )
            projected[variable] = values.astype(np.float32)
            raw_fields[variable].append(
                {
                    "source_path": str(path),
                    "sha256": sha256_file(path),
                    "parser_state": "PASSED",
                    "placeholder": False,
                    "grib_metadata": metadata,
                    **dict(alignment),
                }
            )
        speed, direction_sin, direction_cos = derive_cyclic_wind_direction(
            projected["u10"], projected["v10"]
        )
        meteorology["gfs_u10"].append(projected["u10"])
        meteorology["gfs_v10"].append(projected["v10"])
        meteorology["gfs_wind_speed"].append(speed)
        meteorology["gfs_wind_direction_sin"].append(direction_sin)
        meteorology["gfs_wind_direction_cos"].append(direction_cos)
        meteorology["gfs_t2m"].append(projected["t2m"])
        meteorology["gfs_rh2m"].append(projected["rh2m"])
        meteorology["gfs_surface_pressure"].append(projected["sp"])
        meteorology["gfs_cape"].append(projected["cape"])
        meteorology["gfs_pwat"].append(projected["pwat"])
    channel_to_raw = {
        "gfs_u10": "u10",
        "gfs_v10": "v10",
        "gfs_t2m": "t2m",
        "gfs_rh2m": "rh2m",
        "gfs_surface_pressure": "sp",
        "gfs_cape": "cape",
        "gfs_pwat": "pwat",
    }
    for channel, variable in channel_to_raw.items():
        source_provenance[channel] = raw_fields[variable]
    for channel in ("gfs_wind_speed", "gfs_wind_direction_sin", "gfs_wind_direction_cos"):
        source_provenance[channel] = raw_fields["u10"] + raw_fields["v10"]

    # -----------------------------------------------------------------------
    # PRECIPITATION PATH: PRATE mean-rate conversion (Phase 4E fix)
    #
    # GFS shortName="prate", stepType="avg" is an INTERVAL MEAN RATE in
    # kg m⁻² s⁻¹, NOT a cumulative accumulation.  reconstruct_hourly() is
    # strictly for cumulative APCP fields and MUST NOT be used here.
    #
    # Correct conversion: rate_mm_h = prate_kg_m2_s × 3600
    # No differencing, no previous-field required.
    # Provenance tag: TEMPORALLY_ALIGNED_FROM_NATIVE_PRATE_INTERVAL
    # -----------------------------------------------------------------------
    rainfall, precip_metadata, precip_sources = [], {}, []
    for target in targets:
        end_lead = math.ceil((target - selection.cycle_time).total_seconds() / 3600)
        current_path = (
            granule_directory(cache_root, selection.cycle_time, end_lead) / "prate_mean.grib2"
        )
        # Read the single PRATE field whose native interval covers this target slot.
        current_values, current_lat, current_lon, current_meta = read_field(
            current_path,
            selector("prate_mean", selection.cycle_time, end_lead),
            (72.70, 18.80, 73.10, 19.35),
        )
        # Convert kg m⁻² s⁻¹ → mm/h using the dedicated PRATE path.
        # This validates the field identity (shortName, stepType, units, level)
        # and raises ValueError for any non-physical value.
        rate_mm_h = prate_mean_to_rate(current_values, current_meta)
        rate_spatial, spatial = reproject_rate(
            rate_mm_h, current_lat, current_lon, target_grid
        )
        rainfall.append(rate_spatial.astype(np.float32))
        precip_metadata[end_lead] = current_meta
        precip_sources.append(
            [
                {
                    "source_path": str(current_path),
                    "sha256": sha256_file(current_path),
                    "parser_state": "PASSED",
                    "placeholder": False,
                    "conversion_method": "TEMPORALLY_ALIGNED_FROM_NATIVE_PRATE_INTERVAL",
                    "conversion_formula": "rate_mm_h = prate_kg_m2_s * 3600",
                    "prate_start_step_h": float(current_meta["startStep"]),
                    "prate_end_step_h": float(current_meta["endStep"]),
                    "prate_interval_duration_h": (
                        float(current_meta["endStep"]) - float(current_meta["startStep"])
                    ),
                    "scientific_note": (
                        "PRATE is an interval-mean rate; no accumulation differencing applied. "
                        "Duration does not enter the mm/h conversion."
                    ),
                }
            ]
        )
    precipitation_alignment = align_prate_horizons(issue, selection.cycle_time, precip_metadata)
    source_provenance["gfs_precipitation"] = [
        {**source, **alignment}
        for sources, alignment in zip(precip_sources, precipitation_alignment, strict=True)
        for source in sources
    ]
    arrays = {key: np.stack(value) for key, value in meteorology.items()}
    masks = {key: np.ones(4, dtype=bool) for key in ("gfs_precipitation", *METEOROLOGY_ARRAY_KEYS)}
    return RichIssuePayload(
        event_id=event_id,
        issue_time=issue,
        selection=selection,
        rainfall_rate=np.stack(rainfall),
        meteorology_fields=arrays,
        spatial_metadata=spatial,
        source_provenance=source_provenance,
        temporal_metadata={
            "instantaneous": [dict(value) for value in instant_alignment],
            "precipitation": precipitation_alignment,
        },
        availability_masks=masks,
    )


def plan_rich_replay_for_events(
    events: list[dict[str, Any]],
    assumed_latency_hours: float = 6.0,
    history_length: int = 4,
    prediction_horizon: int = 4,
    temporal_step_minutes: int = 30,
) -> dict[str, Any]:
    """Calculate the required GFS cycles, timestamps, and steps for events without downloading.

    Derives issue times and future targets strictly using the shared authoritative
    build_event_sequences contract (17 sequences per 24-frame event).
    Uses minimal lead selection to avoid overfetching (225 total unique cycle-lead pairs).
    """
    plan: dict[str, Any] = {
        "replay_version": RICH_GFS_REPLAY_VERSION,
        "planned_at": datetime.now(UTC).isoformat(),
        "total_events": len(events),
        "total_issues": 0,
        "train_issues": 0,
        "validation_issues": 0,
        "per_event_issues": 17,
        "unique_cycles_required": set(),
        "_unique_cycle_leads_set": set(),
        "events": {},
    }

    for ev in events:
        event_id = ev["event_id"]
        if is_locked_test_event(event_id):
            raise PermissionError(
                f"Locked test event {event_id} cannot be planned in non-test replay."
            )

        # Derive sequences using shared authoritative sequence index builder
        seqs = build_event_sequences(
            event_id=event_id,
            times=ev.get("times"),
            start_time=ev.get("start_time") or ev.get("start"),
            expected_frames=ev.get("expected_frames", 24),
            history_length=history_length,
            prediction_horizon=prediction_horizon,
            temporal_step_minutes=temporal_step_minutes,
        )

        event_plan: list[dict[str, Any]] = []
        for seq in seqs:
            issue_time_str = seq.input_times[-1]
            issue_dt = utc(issue_time_str)
            sel = select_gfs_forecast_as_of(issue_dt, 120, latency_hours=assumed_latency_hours)
            cycle_str = sel.cycle_time.strftime("%Y%m%d_%H%M")
            plan["unique_cycles_required"].add(cycle_str)

            minimal_leads = select_rich_gfs_leads_for_issue(
                issue_dt, sel.cycle_time, seq.target_times
            )
            for ld in minimal_leads:
                plan["_unique_cycle_leads_set"].add((sel.cycle_time.isoformat(), ld))

            alignment = align_instantaneous_horizons(issue_dt, sel.cycle_time)

            event_plan.append(
                {
                    "sequence_index": seq.start_index,
                    "issue_time": issue_time_str,
                    "target_times": list(seq.target_times),
                    "cycle_time": sel.cycle_time.isoformat(),
                    "cycle_availability_status": "ASSUMED",
                    "availability_time": sel.availability_time.isoformat(),
                    "availability_basis": AVAILABILITY_BASIS,
                    "forecast_hours": list(minimal_leads),
                    "legacy_forecast_hours": list(sel.forecast_hours),
                    "forecast_age_hours": (issue_dt - sel.cycle_time).total_seconds() / 3600.0,
                    "temporal_alignment": alignment,
                }
            )

        split_name = ev.get("split") or ev.get("research_split", "train")
        plan["events"][event_id] = {
            "split": split_name,
            "issues": event_plan,
            "num_issues": len(event_plan),
        }
        plan["total_issues"] += len(event_plan)
        if split_name == "train":
            plan["train_issues"] += len(event_plan)
        elif split_name == "validation":
            plan["validation_issues"] += len(event_plan)

    plan["unique_cycles_required"] = sorted(plan["unique_cycles_required"])
    plan["num_unique_cycles"] = len(plan["unique_cycles_required"])
    plan["unique_cycles_count"] = plan["num_unique_cycles"]
    plan["unique_cycle_leads_required"] = sorted(
        [{"cycle": c, "lead": l} for c, l in plan["_unique_cycle_leads_set"]],
        key=lambda item: (item["cycle"], item["lead"]),
    )
    plan["num_unique_cycle_leads"] = len(plan["unique_cycle_leads_required"])
    plan["unique_cycle_lead_pairs_count"] = plan["num_unique_cycle_leads"]
    plan["overfetch_fixed"] = True
    del plan["_unique_cycle_leads_set"]
    return plan
