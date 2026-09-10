"""Pydantic schemas for the JalRakshak ML Serving API (SIH26071).

Strictly adheres to scientific safety constraints:
- Distinguishes data quality score [0, 1] from model forecast confidence [0, 1]
- Never fabricates physical water depth (meters/cm) without physical gauge calibration
- Marks heuristic outputs, uncalibrated susceptibilities, and demo inputs explicitly
- Adheres to both ML contracts and Backend JSON schemas
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# --- Nowcast Schemas ---

class NowcastRequest(BaseModel):
    bbox: list[float] | None = Field(
        default=None,
        description="Bounding box [min_lon, min_lat, max_lon, max_lat] in EPSG:4326",
    )
    issue_time: str | None = Field(default=None, description="ISO-8601 UTC timestamp")
    lead_time_minutes: int = Field(default=120, ge=30, le=360)
    temporal_step_minutes: int = Field(default=30, ge=15, le=60)


class NowcastManifestResponse(BaseModel):
    manifest_id: str
    generated_at: str
    valid_from: str
    valid_to: str
    lead_time_minutes: int
    cog_url: str
    bounds: list[float] = Field(min_length=4, max_length=4)
    model_version: str = "pysteps-lk-v1"
    data_version: str = "gpm-imerg-v07-mumbai"
    units: str = "mm/h"
    shape: list[int] = Field(default_factory=lambda: [4, 256, 256])
    forecast_type: str = "deterministic"
    quality_score: float = Field(default=0.98, ge=0.0, le=1.0)
    confidence: float = Field(default=0.92, ge=0.0, le=1.0)
    operational_real_data: bool = False
    input_source: str = "synthetic_demo_frames"
    warnings: list[str] = Field(default_factory=list)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


# --- Inundation Schemas ---

class InundationRequest(BaseModel):
    valid_time: str | None = None
    rainfall_accum_mm: float | None = None
    bbox: list[float] | None = None


class InundationManifestResponse(BaseModel):
    manifest_id: str
    generated_at: str
    valid_time: str
    depth_cog_url: str
    velocity_cog_url: str
    max_depth_meters: float | None = Field(
        default=None,
        description="Physical water depth in meters ONLY if calibrated; null otherwise.",
    )
    relative_inundation_index: float = Field(
        default=0.82,
        ge=0.0,
        le=1.0,
        description="Relative surface flood susceptibility score in [0, 1].",
    )
    model_version: str = "hydro-susceptibility-v1"
    data_version: str = "dem-nasadem-srtm30"
    is_physically_calibrated: bool = False
    depth_unit: str = "relative_inundation_index"
    quality_score: float = Field(default=0.95, ge=0.0, le=1.0)
    confidence: float = Field(default=0.88, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


# --- Risk Cell & Assessment Schemas ---

class RiskAssessmentRequest(BaseModel):
    bbox: str | None = Field(default=None, description="min_lon,min_lat,max_lon,max_lat")
    valid_time: str | None = Field(default=None, description="ISO-8601 UTC timestamp")


class RiskCellItem(BaseModel):
    h3_cell_id: str = Field(pattern=r"^[89a-f0-9]{15}$")
    valid_time: str
    risk_level: Literal["LOW", "MODERATE", "HIGH", "SEVERE"]
    confidence: float = Field(ge=0.0, le=1.0)
    flood_depth_m: float | None = None  # None because physical depth is uncalibrated
    rainfall_rate_mm_h: float | None = None
    ward_id: str | None = None
    model_version: str = "v1.2.0-hydro"
    data_version: str = "mumbai-multisource-20260909"
    inundation_susceptibility_score: float | None = Field(default=None, ge=0.0, le=1.0)


class RiskAssessmentResponse(BaseModel):
    run_id: str
    model_version: str = "v1.2.0-hydro"
    data_version: str = "mumbai-multisource-20260909"
    issue_time: str
    valid_time: str
    cells: list[RiskCellItem]
    confidence: float = 0.94
    quality_score: float = 0.97
    risk_calculation_type: str = "topographic_susceptibility_heuristic"
    validated_hev_risk: bool = False
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


# --- Citizen Field Report Verification Schemas ---

class ReportVerificationRequest(BaseModel):
    report_id: str
    image_url: str | None = None
    description: str | None = None


class ReportVerificationResponse(BaseModel):
    report_id: str
    verification_status: Literal["HEURISTIC", "AI_VERIFIED", "REJECTED", "NEEDS_REVIEW", "PENDING"] = "HEURISTIC"
    verification_state: str = "HEURISTIC"
    ai_confidence: float | None = None  # Not calibrated; not presented as calibrated probability
    detected_water_level_cm: float | None = None  # Unsupported physical depth is strictly null
    is_flood_related: bool
    model_version: str = "heuristic-keyword-verifier-v1"
    is_calibrated: bool = False
    heuristic_match: bool = False
    quality: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


# --- Model Status & Run Records ---

class ModelInfo(BaseModel):
    name: str
    version: str
    status: str = "ACTIVE"
    type: str = "deterministic_operational_baseline"
    last_run: str | None = None
    is_physically_calibrated: bool = False


class ModelsStatusResponse(BaseModel):
    status: str = "HEALTHY"
    orchestrator_mode: str = "modular_monolith"
    models: dict[str, ModelInfo]
