"""Layered, rules-only citizen-report corroboration.

The output is an evidence-support decision, never verified flood truth.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


class CitizenVerificationState(str, enum.Enum):
    UNVERIFIED = "UNVERIFIED"
    LOW_SUPPORT = "LOW_SUPPORT"
    PARTIALLY_CORROBORATED = "PARTIALLY_CORROBORATED"
    CORROBORATED = "CORROBORATED"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    REJECTED_SPAM = "REJECTED_SPAM"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class CitizenReportV2:
    report_id: str
    event_id: str
    timestamp: str
    latitude: float
    longitude: float
    h3_index: str | None
    claimed_flood_type: str
    claimed_depth_category: str | None
    text: str
    image_metadata: dict[str, Any] | None = None
    device_source_metadata: dict[str, Any] = field(default_factory=dict)
    duplicate_report_ids: tuple[str, ...] = field(default_factory=tuple)
    rainfall_context_mm_h: float | None = None
    model_hazard_context: float | None = None
    corroborating_report_ids: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if not self.report_id or not self.event_id or not self.text.strip():
            raise ValueError("report_id, event_id, and non-empty text are required")
        parsed = datetime.fromisoformat(self.timestamp)
        if parsed.tzinfo is None:
            raise ValueError("Citizen report timestamp must include a timezone")
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError("Invalid latitude/longitude")
        if self.report_id in self.duplicate_report_ids:
            raise ValueError("A report cannot duplicate itself")
        if self.rainfall_context_mm_h is not None and self.rainfall_context_mm_h < 0:
            raise ValueError("Rainfall rate cannot be negative")
        if self.model_hazard_context is not None and not 0 <= self.model_hazard_context <= 1:
            raise ValueError("Model hazard context must be in [0,1]")


@dataclass(frozen=True)
class LayerResult:
    layer: str
    state: str
    score: float | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CitizenVerificationResultV2:
    report_id: str
    state: CitizenVerificationState
    layers: tuple[LayerResult, ...]
    heuristic_support_score: float | None
    support_score_type: str
    explanation: tuple[str, ...]
    ml_available: bool = False
    verified_flood_truth: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


class CitizenVerificationEngineV2:
    """Apply eight transparent verification layers without trained-ML claims."""

    version = "citizen_verification_v2_rules_only"

    def verify(self, report: CitizenReportV2) -> CitizenVerificationResultV2:
        report.validate()
        layers: list[LayerResult] = [LayerResult("A_SCHEMA", "PASS", 1.0, ("schema valid",))]

        spatial_ok = bool(report.h3_index)
        layers.append(
            LayerResult(
                "B_SPATIOTEMPORAL",
                "PASS" if spatial_ok else "PARTIAL",
                1.0 if spatial_ok else 0.5,
                (
                    "timezone-aware timestamp and valid coordinates",
                    "H3 missing" if not spatial_ok else "H3 present",
                ),
            )
        )

        rain = report.rainfall_context_mm_h
        rain_score = None if rain is None else min(1.0, rain / 20.0)
        layers.append(
            LayerResult(
                "C_RAINFALL",
                "UNAVAILABLE" if rain is None else ("SUPPORT" if rain >= 10 else "WEAK"),
                rain_score,
                ("rainfall is supporting context, not flood proof",),
            )
        )

        nearby = len(set(report.corroborating_report_ids) - set(report.duplicate_report_ids))
        corroboration = min(1.0, nearby / 3.0)
        layers.append(
            LayerResult(
                "D_NEARBY_REPORTS",
                "SUPPORT" if nearby else "NONE",
                corroboration,
                (f"{nearby} non-duplicate nearby reports",),
            )
        )

        spam = (
            len(report.duplicate_report_ids) >= 3
            or report.device_source_metadata.get("spam_flag") is True
        )
        layers.append(
            LayerResult(
                "E_DUPLICATE_SPAM",
                "REJECT" if spam else "PASS",
                0.0 if spam else 1.0,
                (f"{len(report.duplicate_report_ids)} duplicate relationships",),
            )
        )

        image_state = "METADATA_ONLY" if report.image_metadata else "UNAVAILABLE"
        layers.append(
            LayerResult(
                "F_IMAGE",
                image_state,
                None,
                ("no image-content verification model is active",),
            )
        )
        layers.append(
            LayerResult(
                "G_OPTIONAL_ML",
                "UNAVAILABLE",
                None,
                ("no genuine labeled citizen ML is available",),
            )
        )

        present = sum(value is not None for value in (rain_score, report.model_hazard_context))
        support = sum(
            x for x in (rain_score, report.model_hazard_context, corroboration) if x is not None
        ) / max(1, present + 1)
        if spam:
            state = CitizenVerificationState.REJECTED_SPAM
        elif present == 0 and nearby == 0:
            state = CitizenVerificationState.INSUFFICIENT_DATA
        elif rain is not None and rain < 1 and nearby >= 2:
            state = CitizenVerificationState.CONFLICTING_EVIDENCE
        elif nearby >= 2 and support >= 0.55:
            state = CitizenVerificationState.CORROBORATED
        elif nearby >= 1 or support >= 0.45:
            state = CitizenVerificationState.PARTIALLY_CORROBORATED
        elif support > 0:
            state = CitizenVerificationState.LOW_SUPPORT
        else:
            state = CitizenVerificationState.UNVERIFIED

        explanation = (
            "Decision represents heuristic corroboration, not verified flood truth.",
            f"Non-duplicate corroborating reports: {nearby}.",
            "Rainfall and model hazard are contextual associations, not independent ground truth.",
        )
        layers.append(LayerResult("H_DECISION", state.value, round(support, 4), explanation))
        return CitizenVerificationResultV2(
            report_id=report.report_id,
            state=state,
            layers=tuple(layers),
            heuristic_support_score=round(support, 4),
            support_score_type="HEURISTIC_NOT_CALIBRATED_PROBABILITY",
            explanation=explanation,
        )
