"""Advisory-only decision support and deterministic fallbacks."""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass
from typing import Any


class AdvisoryAction(str, enum.Enum):
    WATCH = "WATCH"
    PREPARE = "PREPARE"
    VERIFY_LOCALLY = "VERIFY_LOCALLY"
    ESCALATE_FOR_HUMAN_REVIEW = "ESCALATE_FOR_HUMAN_REVIEW"


@dataclass(frozen=True)
class DecisionSupport:
    action: AdvisoryAction
    reason: str
    evidence: tuple[str, ...]
    confidence: dict[str, Any]
    uncertainty: tuple[str, ...]
    blocking_conditions: tuple[str, ...]
    human_review_required: bool = True
    advisory_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["action"] = self.action.value
        row["government_or_public_order"] = False
        return row


def fallback_matrix(availability: dict[str, bool]) -> dict[str, Any]:
    precipitation = (
        "RADAR"
        if availability.get("radar")
        else (
            "AVAILABLE_PRECIPITATION_SOURCE" if availability.get("precipitation") else "UNAVAILABLE"
        )
    )
    forecast = (
        "NWP_NOWCAST_FUSION"
        if availability.get("fresh_gfs") and availability.get("nowcast")
        else ("NOWCAST_ONLY" if availability.get("nowcast") else "UNAVAILABLE")
    )
    flood = (
        "CALIBRATED_DEPTH"
        if availability.get("calibrated_physics")
        else ("SUSCEPTIBILITY_ONLY" if availability.get("susceptibility") else "UNAVAILABLE")
    )
    if not availability.get("exposure"):
        risk = "NOT_EVALUABLE_MISSING_EXPOSURE"
    elif not availability.get("vulnerability"):
        risk = "REDUCED_EVIDENCE_COMPLETENESS"
    else:
        risk = "EVALUABLE"
    return {
        "precipitation_mode": precipitation,
        "radar_available": bool(availability.get("radar")),
        "forecast_mode": forecast,
        "flood_output_mode": flood,
        "risk_mode": risk,
        "citizen_verification_mode": "ML" if availability.get("citizen_ml") else "RULES_ONLY",
        "citizen_ml_available": bool(availability.get("citizen_ml")),
    }
