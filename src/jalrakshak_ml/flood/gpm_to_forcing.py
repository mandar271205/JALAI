"""GPM rainfall-to-LISFLOOD-FP forcing adapter.

Reads genuine GPM IMERG data cubes (shape: [T, H, W]) from the repository,
computes the domain-average rainfall rate in mm/h at each 30-minute step,
and writes a validated LISFLOOD-FP rainfall boundary (.bdy) file.

Spatial averaging is domain-mean only — sub-grid spatial detail is NOT
invented (GPM 0.1 deg >> 256×256 @ 160m pilot grid).

Does NOT:
- interpolate rainfall to sub-30-min timesteps
- invent spatial variation within the domain
- modify or access Phase 4E training data
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np


_GPM_CUBE_PATTERNS = (
    "data/processed/cubes/gpm_*.npy",
    "data/raw/weather/gpm_*.npy",
    "data/raw/weather/rainfall_*.npy",
)
"""Glob patterns to discover GPM rainfall cubes (Phase 4E training data NOT touched)."""


def discover_gpm_cubes(root: Path | None = None) -> list[Path]:
    """Find GPM rainfall cubes by canonical pattern.

    Training / replay cubes used by Phase 4E are kept separate; this function
    locates genuine GPM files in raw/weather or processed/cubes.
    Phase 4E locked test data is never listed or read here.
    """
    if root is None:
        root = Path(".")
    found = []
    for pattern in _GPM_CUBE_PATTERNS:
        found.extend(sorted(root.glob(pattern)))
    return found


def load_gpm_cube(path: str | Path) -> np.ndarray:
    """Load a GPM rainfall cube and return shape [T, H, W] in mm/h."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"GPM cube not found: {p}")
    if p.suffix == ".npy":
        cube = np.load(p)
    else:
        raise ValueError(f"Unsupported GPM cube format: {p.suffix}")

    if cube.ndim not in (2, 3):
        raise ValueError(f"GPM cube must be 2D [H,W] or 3D [T,H,W]; got {cube.ndim}D")
    if cube.ndim == 2:
        cube = cube[np.newaxis, :, :]  # treat single frame as T=1

    if not np.isfinite(cube).all():
        nan_frac = np.isnan(cube).mean()
        if nan_frac > 0.9:
            raise ValueError(f"GPM cube has {nan_frac:.1%} NaN — likely corrupt or empty")
        # Fill isolated NaN with spatial mean for that timestep
        for t in range(cube.shape[0]):
            frame = cube[t]
            frame_mean = float(np.nanmean(frame))
            cube[t] = np.where(np.isfinite(frame), frame, frame_mean)

    if (cube < 0).any():
        cube = np.clip(cube, 0.0, None)

    return cube.astype(np.float32)


def cube_to_domain_average_rates(cube: np.ndarray) -> np.ndarray:
    """Compute per-timestep domain-average rainfall rate (mm/h).

    Shape in: [T, H, W], shape out: [T]
    """
    if cube.ndim != 3:
        raise ValueError("Expected 3D cube [T,H,W]")
    return cube.mean(axis=(1, 2)).astype(np.float64)


def write_lisflood_bdy(
    rates_mm_h: np.ndarray,
    *,
    event_id: str,
    start_time_iso: str,
    output_path: str | Path,
    cadence_minutes: int = 30,
    overwrite: bool = False,
) -> tuple[Path, dict[str, Any]]:
    """Write a LISFLOOD-FP rainfall boundary (.bdy) file.

    Format:
        rainfall_<event_id>
        N hours
        elapsed_hours   rate_mm_h
        ...
    """
    rates = np.asarray(rates_mm_h, dtype=np.float64)
    if not np.isfinite(rates).all() or (rates < 0).any():
        raise ValueError("Rainfall rates must be finite and non-negative")

    out_path = Path(output_path)
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"Forcing file exists (use overwrite=True): {out_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    start_dt = datetime.fromisoformat(start_time_iso)
    total_steps = len(rates)
    end_dt = start_dt + timedelta(minutes=total_steps * cadence_minutes)

    lines = [
        f"# LISFLOOD-FP rainfall forcing: event {event_id}",
        f"# Source: GPM IMERG V07 domain-average rates",
        f"# Cadence: {cadence_minutes} min  |  Units: mm/h",
        f"# Start: {start_time_iso}  End: {end_dt.isoformat()}",
        f"# Spatial coverage: domain-mean (single areal value per timestep)",
        f"# Sub-grid spatial variation: NOT modelled",
        f"rainfall_{event_id}",
        f"{total_steps} hours",
    ]
    for i, rate in enumerate(rates):
        elapsed_h = (i * cadence_minutes) / 60.0
        lines.append(f"{elapsed_h:.4f}\t{float(rate):.4f}")

    content = "\n".join(lines) + "\n"
    out_path.write_text(content, encoding="utf-8")

    sha256 = hashlib.sha256(out_path.read_bytes()).hexdigest()
    metadata = {
        "event_id": event_id,
        "start_time": start_time_iso,
        "end_time": end_dt.isoformat(),
        "cadence_minutes": cadence_minutes,
        "n_timesteps": total_steps,
        "mean_rate_mm_h": float(rates.mean()),
        "max_rate_mm_h": float(rates.max()),
        "units": "mm/h",
        "spatial_coverage": "domain_mean",
        "sub_grid_spatial_detail": "NOT_MODELLED",
        "source": "gpm_imerg_v07",
        "file_sha256": sha256,
        "forcing_file": str(out_path),
    }

    meta_path = out_path.with_suffix(".json")
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return out_path, metadata


def build_forcing_from_cube(
    cube_path: str | Path,
    *,
    event_id: str,
    start_time_iso: str,
    output_dir: str | Path,
    cadence_minutes: int = 30,
    overwrite: bool = False,
) -> tuple[Path, dict[str, Any]]:
    """End-to-end: load GPM cube → compute domain mean → write .bdy file.

    Returns (bdy_path, metadata_dict).
    """
    cube = load_gpm_cube(cube_path)
    rates = cube_to_domain_average_rates(cube)
    out_path = Path(output_dir) / f"rainfall_{event_id}.bdy"
    return write_lisflood_bdy(
        rates,
        event_id=event_id,
        start_time_iso=start_time_iso,
        output_path=out_path,
        cadence_minutes=cadence_minutes,
        overwrite=overwrite,
    )


def build_forcing_from_existing_bdy(
    bdy_path: str | Path,
) -> dict[str, Any]:
    """Parse an already-written .bdy file and return metadata; does not re-write."""
    bdy = Path(bdy_path)
    if not bdy.is_file():
        raise FileNotFoundError(f"Forcing file missing: {bdy}")

    meta_path = bdy.with_suffix(".json")
    if meta_path.is_file():
        return json.loads(meta_path.read_text(encoding="utf-8"))

    # Parse .bdy if no sidecar .json
    lines = bdy.read_text(encoding="utf-8").splitlines()
    data_lines = [ln for ln in lines if not ln.startswith("#") and ln.strip()]
    rates = []
    for i, ln in enumerate(data_lines):
        if i == 0:
            continue  # event label
        if i == 1:
            continue  # timestep count header
        parts = ln.split()
        if len(parts) >= 2:
            rates.append(float(parts[1]))
    rates_arr = np.array(rates)
    return {
        "forcing_file": str(bdy),
        "n_timesteps": len(rates_arr),
        "mean_rate_mm_h": float(rates_arr.mean()) if rates_arr.size else 0.0,
        "max_rate_mm_h": float(rates_arr.max()) if rates_arr.size else 0.0,
        "units": "mm/h",
        "parsed_from_bdy": True,
        "file_sha256": hashlib.sha256(bdy.read_bytes()).hexdigest(),
    }
