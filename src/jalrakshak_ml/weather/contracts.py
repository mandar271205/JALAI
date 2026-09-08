"""Canonical Meteorological Source Contract for JalRakshak AI (SIH26071).

Provides standardised, decoupled representations for all ingested meteorological
observations (GPM, Radar, INSAT) and NWP fields (GFS), independent from downstream
forecast provider contracts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Sequence

import numpy as np


def _ensure_utc(dt: str | datetime | None) -> datetime | None:
    if dt is None:
        return None
    parsed = datetime.fromisoformat(dt) if isinstance(dt, str) else dt
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(slots=True)
class MeteorologicalField:
    """Canonical representation of a 2D spatial meteorological field.

    Preserves full physical units, native coordinate context, acquisition &
    availability provenance, and quality indicators.

    Important:
    - quality_score is a measure of data health/completeness in [0, 1].
    - It is NEVER model forecast confidence.
    """

    field_name: str
    standard_name: str
    source_name: str
    source_product: str
    source_provider: str

    data: np.ndarray
    valid_mask: np.ndarray

    units: str
    native_units: str
    conversion_method: str

    valid_time: datetime
    acquisition_time: datetime
    availability_time: datetime

    native_resolution: str
    native_cadence_minutes: int
    output_resolution: str
    output_cadence_minutes: int

    source_crs: str
    target_crs: str

    data_version: str
    product_version: str
    processing_version: str

    quality_score: float
    quality_flags: list[str]
    missing_fraction: float

    source_uri: str
    provenance: dict[str, Any] = field(default_factory=dict)
    transformations: list[dict[str, Any]] = field(default_factory=list)

    observation_time: datetime | None = None
    forecast_reference_time: datetime | None = None

    def __post_init__(self) -> None:
        # Array shape and type validation
        self.data = np.asarray(self.data, dtype=np.float32)
        if self.data.ndim != 2:
            raise ValueError(f"MeteorologicalField data must be 2D (y, x), got shape {self.data.shape}")

        self.valid_mask = np.asarray(self.valid_mask, dtype=bool)
        if self.valid_mask.shape != self.data.shape:
            raise ValueError(
                f"valid_mask shape {self.valid_mask.shape} must match data shape {self.data.shape}"
            )

        # Time semantics validation
        self.valid_time = _ensure_utc(self.valid_time)  # type: ignore[assignment]
        self.acquisition_time = _ensure_utc(self.acquisition_time)  # type: ignore[assignment]
        self.availability_time = _ensure_utc(self.availability_time)  # type: ignore[assignment]
        self.observation_time = _ensure_utc(self.observation_time)
        self.forecast_reference_time = _ensure_utc(self.forecast_reference_time)

        if self.valid_time is None or self.acquisition_time is None or self.availability_time is None:
            raise ValueError("valid_time, acquisition_time, and availability_time are strictly required.")

        # If observation field, observation_time should typically be present
        # If NWP forecast field, forecast_reference_time should be present
        if self.observation_time is None and self.forecast_reference_time is None:
            raise ValueError("Either observation_time or forecast_reference_time must be defined.")

        # Quality score & missing fraction bounds
        if not (0.0 <= self.quality_score <= 1.0):
            raise ValueError(f"quality_score must be within [0.0, 1.0], got {self.quality_score}")
        if not (0.0 <= self.missing_fraction <= 1.0):
            raise ValueError(f"missing_fraction must be within [0.0, 1.0], got {self.missing_fraction}")

        # Ensure quality_flags is a list
        if not isinstance(self.quality_flags, list):
            self.quality_flags = list(self.quality_flags)

    @property
    def shape(self) -> tuple[int, int]:
        return self.data.shape

    @property
    def is_observation(self) -> bool:
        return self.observation_time is not None

    @property
    def is_forecast(self) -> bool:
        return self.forecast_reference_time is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to a JSON-serializable dictionary."""
        return {
            "field_name": self.field_name,
            "standard_name": self.standard_name,
            "source_name": self.source_name,
            "source_product": self.source_product,
            "source_provider": self.source_provider,
            "units": self.units,
            "native_units": self.native_units,
            "conversion_method": self.conversion_method,
            "valid_time": self.valid_time.isoformat(),
            "observation_time": self.observation_time.isoformat() if self.observation_time else None,
            "forecast_reference_time": self.forecast_reference_time.isoformat() if self.forecast_reference_time else None,
            "acquisition_time": self.acquisition_time.isoformat(),
            "availability_time": self.availability_time.isoformat(),
            "native_resolution": self.native_resolution,
            "native_cadence_minutes": self.native_cadence_minutes,
            "output_resolution": self.output_resolution,
            "output_cadence_minutes": self.output_cadence_minutes,
            "source_crs": self.source_crs,
            "target_crs": self.target_crs,
            "data_version": self.data_version,
            "product_version": self.product_version,
            "processing_version": self.processing_version,
            "quality_score": float(self.quality_score),
            "quality_flags": list(self.quality_flags),
            "missing_fraction": float(self.missing_fraction),
            "source_uri": self.source_uri,
            "provenance": self.provenance,
            "transformations": self.transformations,
            "shape": list(self.data.shape),
        }
