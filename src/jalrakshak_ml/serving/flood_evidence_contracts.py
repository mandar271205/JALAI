"""Opt-in backend artifact schemas; existing HTTP route behavior remains unchanged."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FloodEvidenceArtifact(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    run_id: str = Field(min_length=1)
    generated_at: datetime
    model_version: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    hazard_type: Literal['susceptibility', 'lisflood_simulated_depth', 'fno_simulated_depth']
    units: Literal['relative_index', 'm']
    api_crs: Literal['EPSG:4326'] = 'EPSG:4326'
    raster_crs: str = Field(min_length=1)
    raster_transform: tuple[float, float, float, float, float, float]
    raster_shape: tuple[int, int]
    artifact_path: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    provenance: dict
    uncertainty: dict
    quality: float = Field(ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: Literal['experimental', 'smoke_only']
    calibrated: Literal[False] = False
    observed: Literal[False] = False
    operational: Literal[False] = False

    @model_validator(mode='after')
    def validate_evidence(self):
        expected = 'relative_index' if self.hazard_type == 'susceptibility' else 'm'
        if self.units != expected or not self.provenance or not self.uncertainty:
            raise ValueError('Hazard units and explicit provenance/uncertainty required')
        if self.generated_at.tzinfo is None or min(self.raster_shape) < 1:
            raise ValueError('Timestamp/grid invalid')
        if self.hazard_type == 'fno_simulated_depth' and self.status != 'smoke_only':
            raise ValueError('Current FNO is smoke_only')
        return self
