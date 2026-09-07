"""Pydantic v2 schema for per-frame weather data manifests.

Every processed weather frame (GPM, GFS, etc.) emits one WeatherFrame
manifest. These are used by the QC pipeline and the data cube assembler.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class WeatherFrame(BaseModel):
    """Canonical manifest for a single processed weather frame."""

    # Identity
    source: str = Field(..., description="Data source identifier, e.g. 'gpm_imerg'")
    variable: str = Field(..., description="Physical variable name, e.g. 'rainfall_rate'")
    valid_time: datetime = Field(..., description="UTC timestamp this frame is valid for")

    # Quality
    quality_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Composite QC score (1.0 = perfect, 0.0 = unusable)"
    )
    missing_percent: float = Field(
        ..., ge=0.0, le=100.0,
        description="Percentage of pixels with missing/nodata values"
    )
    qc_flags: list[str] = Field(
        default_factory=list,
        description="List of QC warnings raised for this frame"
    )

    # Provenance
    processing_version: str = Field(..., description="Version string of processing code")
    data_version: str = Field(..., description="Version/product string of source data")
    source_resolution: str = Field(
        ..., description="Native source resolution, e.g. '0.1 deg' or '3km'"
    )
    canonical_resolution: str = Field(
        ..., description="Output canonical grid resolution, e.g. '~120m @ 256x256'"
    )
    units: str = Field(..., description="Physical units of the variable, e.g. 'mm/h'")
    acquisition_timestamp: datetime = Field(
        ..., description="UTC wall-clock time when data was downloaded/processed"
    )

    # Integrity
    checksum: str = Field(..., description="SHA-256 hex digest of the output array/file")

    @field_validator("valid_time", "acquisition_timestamp", mode="before")
    @classmethod
    def _ensure_utc(cls, v):
        if isinstance(v, str):
            from datetime import timezone
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        return v

    def is_usable(self, min_quality: float = 0.5, max_missing: float = 30.0) -> bool:
        """Return True if this frame meets minimum usability thresholds."""
        return self.quality_score >= min_quality and self.missing_percent <= max_missing
