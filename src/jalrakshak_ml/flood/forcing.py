"""Rainfall to hydraulic solver forcing adapters for SWMM and LISFLOOD-FP.

Preserves 30-minute GPM native cadence and mm/h rate semantics.
Strictly prohibits inventing sub-grid temporal downscaling or false micro-meteorology.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class HydraulicForcingMetadata:
    forcing_id: str
    solver_target: str  # "LISFLOOD-FP" or "SWMM"
    is_observation: bool
    units: str  # must be "mm/h"
    native_cadence_minutes: int  # 30 for GPM
    native_source_resolution: str  # "0.1 deg (~10km)"
    working_grid_shape: list[int]
    start_time: str
    end_time: str
    timesteps_count: int
    mean_rate_mm_h: float
    max_rate_mm_h: float
    source_hash: str
    forcing_file: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HydraulicForcingAdapter:
    """Converts gridded rainfall or event records into hydraulic solver boundary/surface forcing."""

    @staticmethod
    def validate_rates(rates: np.ndarray) -> None:
        if not np.isfinite(rates).all():
            raise ValueError("Rainfall forcing contains NaN or Infinite rates")
        if (rates < 0.0).any():
            raise ValueError("Rainfall forcing rates cannot be negative")

    def build_lisflood_bdy(
        self,
        event_id: str,
        rates_mm_h: list[float] | np.ndarray,
        start_time_iso: str,
        output_path: Path | str,
        is_observation: bool = True,
        cadence_minutes: int = 30,
        grid_shape: tuple[int, int] = (256, 256),
    ) -> tuple[Path, HydraulicForcingMetadata]:
        """Generate LISFLOOD-FP boundary forcing (.bdy) file from 30-minute rainfall rates."""
        rates = np.asarray(rates_mm_h, dtype=np.float32)
        self.validate_rates(rates)

        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        start_dt = datetime.fromisoformat(start_time_iso)
        total_steps = len(rates)
        end_dt = start_dt + timedelta(minutes=total_steps * cadence_minutes)

        # LISFLOOD-FP rainfall boundary format:
        # Header: <id>\n<count> hours\n<time_hours> <rate_mm_h>
        lines = [
            f"# LISFLOOD-FP rainfall forcing for event {event_id}",
            f"# Source: GPM IMERG V07 / Phase 4E Nowcast (native cadence {cadence_minutes}m)",
            "# Units: mm/h",
            f"rainfall_{event_id}",
            f"{total_steps} hours",
        ]

        for i, rate in enumerate(rates):
            elapsed_hours = (i * cadence_minutes) / 60.0
            lines.append(f"{elapsed_hours:.2f}\t{float(rate):.3f}")

        out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        file_bytes = out_file.read_bytes()
        source_hash = hashlib.sha256(file_bytes).hexdigest()

        metadata = HydraulicForcingMetadata(
            forcing_id=f"forcing_{event_id}",
            solver_target="LISFLOOD-FP",
            is_observation=is_observation,
            units="mm/h",
            native_cadence_minutes=cadence_minutes,
            native_source_resolution="0.1 deg (~10km)",
            working_grid_shape=list(grid_shape),
            start_time=start_time_iso,
            end_time=end_dt.isoformat(),
            timesteps_count=total_steps,
            mean_rate_mm_h=float(rates.mean()) if total_steps > 0 else 0.0,
            max_rate_mm_h=float(rates.max()) if total_steps > 0 else 0.0,
            source_hash=source_hash,
            forcing_file=str(out_file),
        )

        meta_file = out_file.with_suffix(".json")
        meta_file.write_text(json.dumps(metadata.to_dict(), indent=2), encoding="utf-8")

        return out_file, metadata

    def build_swmm_dat(
        self,
        station_id: str,
        rates_mm_h: list[float] | np.ndarray,
        start_time_iso: str,
        output_path: Path | str,
        is_observation: bool = True,
        cadence_minutes: int = 30,
    ) -> tuple[Path, HydraulicForcingMetadata]:
        """Generate EPA-SWMM external user rainfall time series (.dat) file."""
        rates = np.asarray(rates_mm_h, dtype=np.float32)
        self.validate_rates(rates)

        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        start_dt = datetime.fromisoformat(start_time_iso)
        total_steps = len(rates)
        end_dt = start_dt + timedelta(minutes=total_steps * cadence_minutes)

        # Standard SWMM user rain file:
        # StationID Year Month Day Hour Minute Value
        lines = [
            f"; SWMM 5 Rainfall File for station {station_id}",
            f"; Units: mm/h (intensity over {cadence_minutes}-minute interval)",
        ]

        for i, rate in enumerate(rates):
            step_dt = start_dt + timedelta(minutes=i * cadence_minutes)
            lines.append(
                f"{station_id} {step_dt.year:04d} {step_dt.month:02d} {step_dt.day:02d} "
                f"{step_dt.hour:02d} {step_dt.minute:02d} {float(rate):.3f}"
            )

        out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        file_bytes = out_file.read_bytes()
        source_hash = hashlib.sha256(file_bytes).hexdigest()

        metadata = HydraulicForcingMetadata(
            forcing_id=f"swmm_forcing_{station_id}",
            solver_target="SWMM",
            is_observation=is_observation,
            units="mm/h",
            native_cadence_minutes=cadence_minutes,
            native_source_resolution="0.1 deg (~10km)",
            working_grid_shape=[1, 1],
            start_time=start_time_iso,
            end_time=end_dt.isoformat(),
            timesteps_count=total_steps,
            mean_rate_mm_h=float(rates.mean()) if total_steps > 0 else 0.0,
            max_rate_mm_h=float(rates.max()) if total_steps > 0 else 0.0,
            source_hash=source_hash,
            forcing_file=str(out_file),
        )

        meta_file = out_file.with_suffix(".json")
        meta_file.write_text(json.dumps(metadata.to_dict(), indent=2), encoding="utf-8")

        return out_file, metadata
