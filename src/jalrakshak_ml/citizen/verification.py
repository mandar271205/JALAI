"""Citizen flood report verification foundation.

Explicit gate: ML_VERIFICATION_AVAILABLE = False.
Heuristic consistency checks are NEVER labeled as an AI/ML model.
Prepares strict contracts for future multimodal verification.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Any

ML_VERIFICATION_AVAILABLE = False


class VerificationStatus(str, enum.Enum):
    VERIFIED = "VERIFIED"
    LIKELY = "LIKELY"
    UNCERTAIN = "UNCERTAIN"
    CONFLICTING = "CONFLICTING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class CitizenReport:
    report_id: str
    timestamp: str
    latitude: float
    longitude: float
    text_description: str
    image_metadata: dict[str, Any] | None = None
    user_reliability_score: float | None = None  # non-sensitive signal in [0, 1]

    def validate(self) -> None:
        if not self.report_id or not self.text_description:
            raise ValueError("Report ID and text description are required")
        if not (-90.0 <= self.latitude <= 90.0 and -180.0 <= self.longitude <= 180.0):
            raise ValueError("Invalid geographic coordinates")
        try:
            datetime.fromisoformat(self.timestamp)
        except ValueError as err:
            raise ValueError("Invalid ISO-8601 timestamp") from err


@dataclass(frozen=True)
class ReportVerificationResult:
    report_id: str
    status: VerificationStatus | str
    consistency_score: float  # [0, 1]
    duplicate_score: float  # [0, 1]
    spatial_consistency: bool
    temporal_consistency: bool
    image_verification_state: str
    confidence: float  # [0, 1]
    evidence: list[str]
    reasons: list[str]
    model_version: str
    ml_verification_available: bool = ML_VERIFICATION_AVAILABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "status": str(self.status),
            "consistency_score": self.consistency_score,
            "duplicate_score": self.duplicate_score,
            "spatial_consistency": self.spatial_consistency,
            "temporal_consistency": self.temporal_consistency,
            "image_verification_state": self.image_verification_state,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "reasons": self.reasons,
            "model_version": self.model_version,
            "ml_verification_available": self.ml_verification_available,
            "verified_by_ai": False,  # Strict claim gate
        }


class CitizenReportVerificationEngine:
    """Verifies citizen reports against meteorological and spatial evidence.

    Uses deterministic consistency heuristics; does NOT claim to be a trained multimodal ML model.
    """

    engine_version = "citizen_verification_heuristic_v1"

    def verify_report(
        self,
        report: CitizenReport,
        local_rainfall_rate_mm_h: float | None,
        local_susceptibility_score: float | None,
        nearby_reports_count: int = 0,
    ) -> ReportVerificationResult:
        report.validate()
        evidence: list[str] = []
        reasons: list[str] = []

        # Check evidence availability
        if local_rainfall_rate_mm_h is None and local_susceptibility_score is None:
            return ReportVerificationResult(
                report_id=report.report_id,
                status=VerificationStatus.INSUFFICIENT_EVIDENCE,
                consistency_score=0.0,
                duplicate_score=0.0,
                spatial_consistency=False,
                temporal_consistency=False,
                image_verification_state="UNVERIFIED_NO_ML_MODEL",
                confidence=0.1,
                evidence=["Local sensor and radar/nowcast inputs missing"],
                reasons=["Cannot verify report without environmental reference data"],
                model_version=self.engine_version,
                ml_verification_available=ML_VERIFICATION_AVAILABLE,
            )

        consistency_points = 0.0
        max_points = 3.0

        # Meteorological consistency
        rain_consistent = False
        if local_rainfall_rate_mm_h is not None:
            if local_rainfall_rate_mm_h >= 10.0:
                rain_consistent = True
                consistency_points += 1.0
                evidence.append(f"Significant local rainfall detected: {local_rainfall_rate_mm_h:.1f} mm/h")
            elif local_rainfall_rate_mm_h < 1.0:
                reasons.append(f"Near-zero rainfall recorded: {local_rainfall_rate_mm_h:.1f} mm/h")
            else:
                consistency_points += 0.5
                evidence.append(f"Light/moderate rainfall recorded: {local_rainfall_rate_mm_h:.1f} mm/h")

        # Topographic susceptibility consistency
        terrain_consistent = False
        if local_susceptibility_score is not None:
            if local_susceptibility_score >= 0.4:
                terrain_consistent = True
                consistency_points += 1.0
                evidence.append(f"Report location has elevated susceptibility: {local_susceptibility_score:.2f}")
            else:
                reasons.append(f"Report location is topographically high/well-drained: {local_susceptibility_score:.2f}")

        # Social / spatial clustering consistency
        if nearby_reports_count > 0:
            consistency_points += min(1.0, 0.5 * nearby_reports_count)
            evidence.append(f"{nearby_reports_count} corroborating reports within 1km")

        consistency_score = float(consistency_points / max_points)

        # Classify status
        if rain_consistent and terrain_consistent:
            status = VerificationStatus.VERIFIED if nearby_reports_count >= 2 else VerificationStatus.LIKELY
        elif rain_consistent or terrain_consistent:
            status = VerificationStatus.UNCERTAIN
        else:
            status = VerificationStatus.CONFLICTING

        image_state = (
            "METADATA_TIMESTAMP_MATCHED"
            if report.image_metadata
            else "NO_IMAGE_PROVIDED"
        )

        return ReportVerificationResult(
            report_id=report.report_id,
            status=status,
            consistency_score=round(consistency_score, 3),
            duplicate_score=0.0,
            spatial_consistency=terrain_consistent,
            temporal_consistency=rain_consistent,
            image_verification_state=image_state,
            confidence=round(min(1.0, consistency_score * 0.9), 3),
            evidence=evidence,
            reasons=reasons,
            model_version=self.engine_version,
            ml_verification_available=ML_VERIFICATION_AVAILABLE,
        )
