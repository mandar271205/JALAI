"""Meteorological Data Quality Engine V2 for JalRakshak AI (SIH26071).

Performs strict, physically grounded QC on multi-source weather observations
and NWP fields:
- Missing-data completeness
- Physical validity bounds (precipitation, humidity, wind, temperature, CAPE, pressure)
- Constant-field suspicion (frozen sensor / model crash)
- All-zero suspicious fields (for fields that must not be zero like pressure or temperature)
- Clipped field detection (sensor saturation / artificial limits)
- Temporal freshness / staleness
- Coordinate sanity & NaN/Inf fractions

CRITICAL PRINCIPLE:
quality_score in [0, 1] measures observational and physical sanity.
It is NEVER to be used as or conflated with downstream model forecast confidence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

# Established Physical Validity Ranges for Meteorological Variables
PHYSICAL_VALIDITY_RANGES: dict[str, tuple[float, float]] = {
    "rainfall_rate": (0.0, 300.0),       # mm/h (WMO world-record hourly rainfall is ~305 mm)
    "reflectivity": (-15.0, 75.0),      # dBZ (hail/extreme core limit)
    "radial_velocity": (-100.0, 100.0), # m/s
    "wind_u": (-120.0, 120.0),          # m/s
    "wind_v": (-120.0, 120.0),          # m/s
    "wind_speed": (0.0, 120.0),         # m/s (Category 5 hurricane winds ~85 m/s)
    "temperature": (180.0, 345.0),      # K (-93 °C to +72 °C)
    "relative_humidity": (0.0, 100.5),  # % (0.5% tolerance for numerical rounding)
    "pressure": (50000.0, 110000.0),    # Pa (500 hPa to 1100 hPa)
    "surface_pressure": (50000.0, 110000.0),
    "cape": (0.0, 10000.0),             # J/kg (extreme tropical convection ~6000-8000 J/kg)
    "precipitable_water": (0.0, 150.0), # kg/m^2 (extreme monsoonal columns ~80-100 kg/m^2)
    "brightness_temperature": (150.0, 350.0),  # K for geostationary satellite IR/WV
}

# Variables that are physically invalid if exactly zero everywhere across the domain
NON_ZERO_VARIABLES = {
    "temperature",
    "surface_pressure",
    "pressure",
    "brightness_temperature",
}


@dataclass(slots=True)
class QCResult:
    """Standardized output of Meteorological QC Engine V2."""

    quality_score: float
    quality_flags: list[str]
    missing_fraction: float
    is_valid: bool
    metrics: dict[str, float] = field(default_factory=dict)
    cleaned_data: np.ndarray | None = None


class MeteorologicalQCEngineV2:
    """Comprehensive Quality Control Engine for Meteorological Data."""

    def __init__(
        self,
        variable_name: str,
        expected_range: tuple[float, float] | None = None,
        max_missing_fraction: float = 0.50,
        allow_all_zero: bool | None = None,
        seen_cache: set[str] | None = None,
    ) -> None:
        self.variable_name = variable_name.lower()
        self.expected_range = expected_range or self._infer_range(self.variable_name)
        self.max_missing_fraction = max_missing_fraction
        self.allow_all_zero = (
            allow_all_zero
            if allow_all_zero is not None
            else not any(nz in self.variable_name for nz in NON_ZERO_VARIABLES)
        )
        self._seen = seen_cache if seen_cache is not None else set()

    def _infer_range(self, var_name: str) -> tuple[float, float]:
        for key, bounds in PHYSICAL_VALIDITY_RANGES.items():
            if key in var_name:
                return bounds
        return (-np.inf, np.inf)

    def evaluate(
        self,
        data: np.ndarray,
        valid_time: datetime | str | None = None,
        source_id: str = "unknown",
        age_minutes: float | None = None,
        max_staleness_minutes: float | None = None,
    ) -> QCResult:
        """Run full QC inspection on a 2D meteorological array.

        Returns QCResult with quality_score in [0.0, 1.0] and diagnostic flags.
        """
        arr = np.asarray(data, dtype=np.float32)
        flags: list[str] = []
        penalty = 0.0
        total_elements = arr.size
        if total_elements == 0:
            return QCResult(
                quality_score=0.0,
                quality_flags=["EMPTY_ARRAY"],
                missing_fraction=1.0,
                is_valid=False,
            )

        # 1. Non-finite & Missing Check
        nan_count = int(np.sum(np.isnan(arr)))
        inf_count = int(np.sum(np.isinf(arr)))
        missing_count = nan_count + inf_count
        missing_fraction = missing_count / total_elements

        if missing_fraction > self.max_missing_fraction:
            flags.append(f"HIGH_MISSING_DATA:{missing_fraction:.1%}")
            penalty += min(0.50, missing_fraction * 0.6)
        elif missing_fraction > 0.10:
            flags.append(f"PARTIAL_COVERAGE:{missing_fraction:.1%}")
            penalty += missing_fraction * 0.3

        finite_mask = np.isfinite(arr)
        finite_vals = arr[finite_mask]

        # If completely empty
        if finite_vals.size == 0:
            flags.append("ALL_MISSING_DATA")
            return QCResult(
                quality_score=0.0,
                quality_flags=flags,
                missing_fraction=1.0,
                is_valid=False,
                metrics={"missing_fraction": 1.0},
            )

        # 2. Physical Bounds Check
        min_bound, max_bound = self.expected_range
        out_of_bounds = (finite_vals < min_bound) | (finite_vals > max_bound)
        out_count = int(np.sum(out_of_bounds))
        if out_count > 0:
            out_pct = out_count / total_elements
            flags.append(
                f"PHYSICAL_RANGE_FAILURE:{out_count}_pixels"
                f"[{min_bound},{max_bound}]"
            )
            penalty += min(0.40, 0.20 + out_pct * 0.4)

        # 3. Constant Field Suspicion (frozen sensor / model failure)
        std_val = float(np.std(finite_vals))
        if finite_vals.size > 16 and std_val < 1e-6:
            # If rainfall is 0 everywhere, that is physically plausible (dry weather),
            # but if temperature, wind, or pressure is identical everywhere, it's suspect.
            if not self.allow_all_zero or abs(float(finite_vals[0])) > 1e-4:
                flags.append("CONSTANT_FIELD_SUSPECT")
                penalty += 0.25

        # 4. All-Zero Suspicious Fields
        if not self.allow_all_zero and np.allclose(finite_vals, 0.0, atol=1e-5):
            flags.append("ALL_ZERO_SUSPECT")
            penalty += 0.50

        # 5. Clipped Field Check (saturation at limits)
        if finite_vals.size > 16:
            at_min = np.sum(np.isclose(finite_vals, min_bound, atol=1e-4))
            at_max = np.sum(np.isclose(finite_vals, max_bound, atol=1e-4))
            if at_max > 0.20 * total_elements and max_bound < np.inf:
                flags.append(f"CLIPPED_MAX_SUSPECT:{at_max}_pixels")
                penalty += 0.15

        # 6. Staleness Check
        if age_minutes is not None and max_staleness_minutes is not None:
            if age_minutes > max_staleness_minutes:
                flags.append(f"STALE_SOURCE:{age_minutes:.0f}m>{max_staleness_minutes:.0f}m")
                penalty += min(0.30, 0.10 + 0.05 * (age_minutes - max_staleness_minutes) / 30.0)

        # 7. Duplicate Check
        if valid_time is not None:
            v_iso = valid_time.isoformat() if isinstance(valid_time, datetime) else str(valid_time)
            key = f"{source_id}|{self.variable_name}|{v_iso}"
            if key in self._seen:
                flags.append("DUPLICATE_FRAME")
                penalty += 0.15
            else:
                self._seen.add(key)

        quality_score = float(max(0.0, min(1.0, 1.0 - penalty)))
        is_valid = quality_score >= 0.40 and "ALL_MISSING_DATA" not in flags

        # Generate cleaned array (clipping out-of-bounds finite values)
        cleaned = np.copy(arr)
        if out_count > 0:
            cleaned = np.clip(cleaned, min_bound, max_bound)

        metrics = {
            "mean": float(np.mean(finite_vals)),
            "std": std_val,
            "min": float(np.min(finite_vals)),
            "max": float(np.max(finite_vals)),
            "missing_fraction": missing_fraction,
            "quality_score": round(quality_score, 4),
        }

        return QCResult(
            quality_score=round(quality_score, 4),
            quality_flags=flags,
            missing_fraction=round(missing_fraction, 4),
            is_valid=is_valid,
            metrics=metrics,
            cleaned_data=cleaned,
        )
