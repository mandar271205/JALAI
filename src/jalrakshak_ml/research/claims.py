"""Central executable scientific-claim registry."""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass
from typing import Any


class ClaimStatus(str, enum.Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ClaimDecision:
    claim_id: str
    status: ClaimStatus
    required_evidence: tuple[str, ...]
    present_evidence: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    safe_phrase: str
    forbidden_phrase: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


CLAIMS = {
    "FLOOD_DEPTH": (
        ("calibrated_depth", "genuine_hydraulic_or_validated_surrogate"),
        "Modeled flood depth from a validated hydraulic source",
        "Flood depth unavailable; relative susceptibility only",
        "Flood depth predicted",
    ),
    "FLOOD_SUSCEPTIBILITY": (
        ("susceptibility_output",),
        "Relative flood susceptibility is high",
        "Flood susceptibility unavailable",
        "Observed flood depth is high",
    ),
    "CITIZEN_VERIFIED": (
        ("corroborated_official_or_sensor_evidence",),
        "Citizen report corroborated by cited independent evidence",
        "Citizen report heuristic corroboration status",
        "Citizen report is verified flood truth",
    ),
    "REALTIME_RADAR_NOWCAST": (
        ("actual_radar_source", "radar_fresh"),
        "Real-time radar nowcast from the cited fresh radar source",
        "Available precipitation-source nowcast",
        "Real-time radar nowcast",
    ),
    "CALIBRATED_PROBABILITY": (
        ("calibration_metrics", "held_out_calibration"),
        "Calibrated probability on the cited held-out evaluation",
        "Heuristic score",
        "Calibrated probability",
    ),
}


def evaluate_claim(claim_id: str, present_evidence: set[str]) -> ClaimDecision:
    if claim_id not in CLAIMS:
        raise KeyError(f"Unknown scientific claim: {claim_id}")
    required, allowed_phrase, blocked_phrase, forbidden = CLAIMS[claim_id]
    missing = tuple(item for item in required if item not in present_evidence)
    status = ClaimStatus.BLOCKED if missing else ClaimStatus.ALLOWED
    return ClaimDecision(
        claim_id=claim_id,
        status=status,
        required_evidence=required,
        present_evidence=tuple(sorted(present_evidence)),
        blocking_reasons=tuple(f"missing:{item}" for item in missing),
        safe_phrase=blocked_phrase if status is ClaimStatus.BLOCKED else allowed_phrase,
        forbidden_phrase=forbidden,
    )


def evaluate_all(present_evidence: set[str]) -> list[ClaimDecision]:
    return [evaluate_claim(claim_id, present_evidence) for claim_id in CLAIMS]
