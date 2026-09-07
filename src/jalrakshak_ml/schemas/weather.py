from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class WeatherFrame(BaseModel):
    source: str
    variable: str
    valid_time: datetime
    bbox: tuple[float, float, float, float]
    crs: str
    resolution_m: float = Field(gt=0)
    units: str
    quality_score: float = Field(ge=0.0, le=1.0)
    object_uri: str
    checksum: str

    freshness_score: float | None = Field(default=None, ge=0.0, le=1.0)
    missing_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    processing_version: str = "0.1.0"
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("bbox")
    @classmethod
    def bbox_order(cls, v: tuple[float, float, float, float]):
        west, south, east, north = v
        if not (west < east and south < north):
            raise ValueError("bbox must be [west, south, east, north].")
        return v
