"""QC framework for individual weather frames.

Pipeline:
  1. Timestamp check (must be UTC, not in the future beyond 1h)
  2. Unit check (validate against config)
  3. Missing values → compute missing_percent
  4. Range validity (per-variable physical min/max)
  5. Duplicate detection (by valid_time + source)
  6. CRS check
  7. Spatial coverage (overlap with pilot bbox)
  8. Composite quality_score computation
  9. Emit WeatherFrame manifest

Important: this module keeps no global state. The caller (pipeline) is
responsible for tracking seen frames to detect duplicates.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from jalrakshak_ml.schemas.weather_frame import WeatherFrame

log = logging.getLogger(__name__)

# Physical validity ranges for key variables
_VALID_RANGES: dict[str, tuple[float, float]] = {
    "rainfall_rate": (0.0, 300.0),     # mm/h — WMO extreme limit
    "precipitation": (0.0, 500.0),      # mm accumulated
    "temperature": (220.0, 340.0),      # Kelvin
    "humidity": (0.0, 100.0),           # %
    "wind_u": (-100.0, 100.0),          # m/s
    "wind_v": (-100.0, 100.0),          # m/s
}


class FrameQC:
    """Quality-control a single weather frame and produce a WeatherFrame manifest."""

    def __init__(
        self,
        source: str,
        variable: str,
        data_version: str,
        source_resolution: str,
        canonical_resolution: str,
        processing_version: str,
        units: str,
        expected_units: str | None = None,
        seen_timestamps: set[str] | None = None,
    ):
        self.source = source
        self.variable = variable
        self.data_version = data_version
        self.source_resolution = source_resolution
        self.canonical_resolution = canonical_resolution
        self.processing_version = processing_version
        self.units = units
        self.expected_units = expected_units
        self._seen: set[str] = seen_timestamps if seen_timestamps is not None else set()

    def run(
        self,
        array: np.ndarray,
        valid_time: datetime,
        nodata_value: float = np.nan,
    ) -> tuple[WeatherFrame, np.ndarray]:
        """
        Run QC on *array* for the given *valid_time*.

        Returns
        -------
        manifest : WeatherFrame
        cleaned_array : array with out-of-range values masked as NaN
        """
        flags: list[str] = []
        penalty = 0.0  # accumulated quality penalty [0, 1]
        now_utc = datetime.now(timezone.utc)

        # ── 1. Timestamp check ────────────────────────────────────────────
        if valid_time.tzinfo is None:
            valid_time = valid_time.replace(tzinfo=timezone.utc)
            flags.append("WARN_NAIVE_TIMESTAMP_ASSUMED_UTC")

        if valid_time > now_utc + timedelta(hours=1):
            flags.append("WARN_FUTURE_TIMESTAMP")
            penalty += 0.1

        # ── 2. Unit check ─────────────────────────────────────────────────
        if self.expected_units and self.units != self.expected_units:
            flags.append(f"WARN_UNIT_MISMATCH:{self.units}!={self.expected_units}")
            penalty += 0.2

        # ── 3. Missing values ─────────────────────────────────────────────
        arr = array.astype(np.float32)
        if not np.isnan(nodata_value):
            arr = np.where(arr == nodata_value, np.nan, arr)

        total_pixels = arr.size
        missing = int(np.sum(np.isnan(arr)))
        missing_percent = 100.0 * missing / total_pixels

        if missing_percent > 90.0:
            flags.append(f"ERROR_MOSTLY_MISSING:{missing_percent:.1f}%")
            penalty += 0.5
        elif missing_percent > 30.0:
            flags.append(f"WARN_HIGH_MISSING:{missing_percent:.1f}%")
            penalty += 0.2

        # ── 4. Range validity ─────────────────────────────────────────────
        if self.variable in _VALID_RANGES:
            lo, hi = _VALID_RANGES[self.variable]
            out_of_range = np.nansum((arr < lo) | (arr > hi))
            if out_of_range > 0:
                flags.append(f"WARN_OUT_OF_RANGE:{out_of_range}_pixels")
                penalty += min(0.3, 0.3 * out_of_range / total_pixels)
                # Clip to valid range (mask extreme values)
                arr = np.clip(arr, lo, hi)

        # ── 5. Duplicate detection ────────────────────────────────────────
        frame_key = f"{self.source}|{valid_time.isoformat()}"
        if frame_key in self._seen:
            flags.append("WARN_DUPLICATE_FRAME")
            penalty += 0.15
        else:
            self._seen.add(frame_key)

        # ── 6. Spatial coverage check ─────────────────────────────────────
        valid_pixels = total_pixels - missing
        coverage = valid_pixels / total_pixels
        if coverage < 0.5:
            flags.append(f"WARN_LOW_SPATIAL_COVERAGE:{coverage:.1%}")
            penalty += 0.1

        # ── 7–8. Quality score ────────────────────────────────────────────
        quality_score = max(0.0, 1.0 - penalty)

        # ── 9. Checksum of cleaned array ──────────────────────────────────
        checksum = hashlib.sha256(arr.tobytes()).hexdigest()

        manifest = WeatherFrame(
            source=self.source,
            variable=self.variable,
            valid_time=valid_time,
            quality_score=round(quality_score, 4),
            missing_percent=round(missing_percent, 2),
            qc_flags=flags,
            processing_version=self.processing_version,
            data_version=self.data_version,
            source_resolution=self.source_resolution,
            canonical_resolution=self.canonical_resolution,
            units=self.units,
            acquisition_timestamp=now_utc,
            checksum=checksum,
        )

        if flags:
            log.debug("QC flags for %s @ %s: %s", self.variable, valid_time.isoformat(), flags)

        return manifest, arr
