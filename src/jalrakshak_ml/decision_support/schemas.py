"""Pydantic schemas and typed contracts for JalRakshak AI Decision Support Inference.

Strictly adheres to scientific constraints:
- Discrete enums for severity, trend, source mode, and verifier verdicts
- Normalized confidence clamped [0.0, 1.0]
- Unsupported physical flood depth (meters) must remain null
- Rainfall intensity bands bounded by meteorological evidence
- Separation of numerical model truth from AI operational narratives
- Truthful provenance preserving auditability without exposing provider names to UI
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InferenceMode(str, Enum):
    """Authoritative source mode for inference responses."""
    NUMERICAL_MODEL = "NUMERICAL_MODEL"
    MODEL_PLUS_AI = "MODEL_PLUS_AI"
    PROVISIONAL_AI = "PROVISIONAL_AI"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class SeverityLevel(str, Enum):
    """Categorical severity for rainfall and flood risk."""
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


class TrendDirection(str, Enum):
    """Temporal evolution trend for rainfall or flood risk."""
    DECREASING = "DECREASING"
    STABLE = "STABLE"
    INCREASING = "INCREASING"
    UNKNOWN = "UNKNOWN"


class VerifierVerdict(str, Enum):
    """Judgment verdicts from the Heavy Verifier (Model 3)."""
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    DOWNGRADE = "DOWNGRADE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class IntensityBand(BaseModel):
    """Expected intensity range in mm/h."""
    model_config = ConfigDict(extra="ignore")

    min: float | None = Field(default=None, description="Minimum expected intensity (mm/h)")
    max: float | None = Field(default=None, description="Maximum expected intensity (mm/h)")


class InferenceProvenance(BaseModel):
    """Truthful internal audit metadata for inference decisions."""
    model_config = ConfigDict(extra="ignore")

    source_mode: InferenceMode
    primary_model_available: bool
    numerical_model_name: str | None = None
    numerical_model_version: str | None = None
    ai_assistance_used: bool = False
    ai_generation_used: bool = False
    ai_generator_slot: int | None = None
    ai_generator_provider: str | None = None
    ai_generator_model: str | None = None
    ai_failover_used: bool = False
    ai_failover_reason: str | None = None
    ai_verifier_used: bool = False
    ai_verifier_provider: str | None = None
    ai_verifier_model: str | None = None
    ai_verifier_verdict: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    data_version: str | None = None
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# ==============================================================================
# Rainfall Contracts
# ==============================================================================

class RainfallInferenceInput(BaseModel):
    """Input payload containing numerical model results or meteorological evidence."""
    model_config = ConfigDict(extra="ignore")

    forecast_horizons_minutes: list[int] = Field(default_factory=lambda: [30, 60, 90, 120])
    rainfall_mm_h: list[float] | None = None
    probability_gt_1: list[float] | None = None
    probability_gt_5: list[float] | None = None
    probability_gt_10: list[float] | None = None
    quality_score: float | None = None
    model_confidence: float | None = None
    model_name: str | None = None
    model_version: str | None = None
    data_version: str | None = None
    gfs_context: dict[str, Any] | None = None
    recent_observation_trend: str | None = None
    latest_observation_mm_h: float | None = None
    persistence_baseline_mm_h: float | None = None
    timestamp: str | None = None
    location: dict[str, Any] | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    citizen_reports_summary: str | None = None
    untrusted_user_input: str | None = None


class RainfallCandidateResult(BaseModel):
    """Raw structured output produced by an external LLM generator for rainfall."""
    model_config = ConfigDict(extra="ignore")

    severity: SeverityLevel
    trend: TrendDirection
    confidence: float = Field(ge=0.0, le=1.0)
    expected_intensity_band_mm_h: IntensityBand = Field(default_factory=IntensityBand)
    summary: str
    key_factors: list[str] = Field(default_factory=list)
    recommended_action: str
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        try:
            val = float(v)
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.5


class RainfallInferenceOutput(BaseModel):
    """Canonical domain output for rainfall inference."""
    model_config = ConfigDict(extra="ignore")

    severity: SeverityLevel
    trend: TrendDirection
    confidence: float = Field(ge=0.0, le=1.0)
    expected_intensity_band_mm_h: IntensityBand = Field(default_factory=IntensityBand)
    summary: str
    key_factors: list[str] = Field(default_factory=list)
    recommended_action: str
    evidence_ids: list[str] = Field(default_factory=list)
    numerical_forecast: dict[str, Any] | None = None
    provenance: InferenceProvenance


# ==============================================================================
# Flood Contracts
# ==============================================================================

class FloodInferenceInput(BaseModel):
    """Input payload containing physics solver output or geospatial evidence."""
    model_config = ConfigDict(extra="ignore")

    rainfall_forcing_mm_h: float | None = None
    dem_elevation_m: float | None = None
    slope_degrees: float | None = None
    susceptibility_score: float | None = None
    distance_to_drainage_m: float | None = None
    exposure_score: float | None = None
    vulnerability_score: float | None = None
    hev_risk_score: float | None = None
    critical_assets: list[str] = Field(default_factory=list)
    numerical_model_output: dict[str, Any] | None = None
    model_name: str | None = None
    model_version: str | None = None
    quality_score: float | None = None
    model_confidence: float | None = None
    location: dict[str, Any] | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    citizen_reports_summary: str | None = None
    untrusted_user_input: str | None = None


class FloodCandidateResult(BaseModel):
    """Raw structured output produced by an external LLM generator for flood."""
    model_config = ConfigDict(extra="ignore")

    risk_level: SeverityLevel
    confidence: float = Field(ge=0.0, le=1.0)
    depth_m: float | None = None
    dominant_factors: list[str] = Field(default_factory=list)
    summary: str
    recommended_action: str
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        try:
            val = float(v)
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.5


class FloodInferenceOutput(BaseModel):
    """Canonical domain output for flood inference."""
    model_config = ConfigDict(extra="ignore")

    risk_level: SeverityLevel
    confidence: float = Field(ge=0.0, le=1.0)
    depth_m: float | None = None
    dominant_factors: list[str] = Field(default_factory=list)
    summary: str
    recommended_action: str
    evidence_ids: list[str] = Field(default_factory=list)
    numerical_model_output: dict[str, Any] | None = None
    provenance: InferenceProvenance


# ==============================================================================
# Heavy Verifier (Model 3) Contracts
# ==============================================================================

class VerifierInput(BaseModel):
    """Input payload provided to Model 3 for structured verification."""
    model_config = ConfigDict(extra="ignore")

    domain: str
    evidence: dict[str, Any]
    numerical_model_result: dict[str, Any] | None = None
    candidate_ai_result: dict[str, Any]
    source_mode: str
    data_quality: float | None = None
    model_confidence: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class VerifierOutput(BaseModel):
    """Strict structured evaluation from Model 3."""
    model_config = ConfigDict(extra="ignore")

    verdict: VerifierVerdict
    agreement_score: float = Field(ge=0.0, le=1.0)
    evidence_support_score: float = Field(ge=0.0, le=1.0)
    identified_conflicts: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    recommended_severity: SeverityLevel | None = None
    reason: str

    @field_validator("agreement_score", "evidence_support_score", mode="before")
    @classmethod
    def clamp_scores(cls, v: Any) -> float:
        try:
            val = float(v)
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.5


# ==============================================================================
# Service Status Contracts
# ==============================================================================

class DecisionSupportStatusResponse(BaseModel):
    """Health and configuration inspection surface for internal status."""
    model_config = ConfigDict(extra="ignore")

    status: str = "HEALTHY"
    rainfall_model_available: bool
    rainfall_model_name: str | None
    rainfall_model_status: str
    flood_model_available: bool
    flood_model_name: str | None
    flood_model_status: str
    ai_enabled: bool
    primary_ai_provider: str
    secondary_ai_provider: str
    verifier_ai_provider: str
    provider_health: dict[str, Any] = Field(default_factory=dict)
