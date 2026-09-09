"""Structured risk explanation with evidence-completeness warnings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from jalrakshak_ml.research.confidence import CompositeConfidence


@dataclass(frozen=True)
class RiskExplanationV2:
    risk_tier: str
    risk_score: float | None
    hazard_contribution: dict[str, Any]
    exposure_contribution: dict[str, Any]
    vulnerability_contribution: dict[str, Any]
    uncertainty: dict[str, Any]
    confidence_components: CompositeConfidence
    top_drivers: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    freshness_warnings: tuple[str, ...]
    scientific_caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        self.confidence_components.validate()
        payload = asdict(self)
        payload["confidence_components"] = self.confidence_components.to_dict()
        payload["causal_social_claims_made"] = False
        return payload


def explain_risk_v2(
    *,
    tier: str,
    score: float | None,
    hazard: float | None,
    exposure: float | None,
    vulnerability: float | None,
    confidence: CompositeConfidence,
    missing_evidence: tuple[str, ...] = (),
    freshness_warnings: tuple[str, ...] = (),
) -> RiskExplanationV2:
    drivers: list[str] = []
    if hazard is not None and hazard >= 0.6:
        drivers.append("elevated modeled hazard")
    if exposure is not None and exposure >= 0.6:
        drivers.append("high exposure density")
    if vulnerability is not None and vulnerability >= 0.6:
        drivers.append("elevated vulnerability proxy")
    return RiskExplanationV2(
        tier,
        score,
        {"score": hazard, "semantics": "susceptibility_or_validated_hazard_as_declared"},
        {"score": exposure},
        {"score": vulnerability, "causal_interpretation": False},
        {"status": "explicit_components_preserved"},
        confidence,
        tuple(drivers),
        missing_evidence,
        freshness_warnings,
        (
            "Model contributions are associations, not causal social claims.",
            "Susceptibility is not water depth.",
        ),
    )
