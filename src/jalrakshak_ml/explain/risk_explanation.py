"""Machine- and human-readable flood-risk explanations without causal overclaiming.

Provides decision-ready evidence, top drivers, and explicit uncertainty boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RiskExplanation:
    rainfall_contribution: dict[str, Any]
    terrain_or_flood_contribution: dict[str, Any]
    exposure_contribution: dict[str, Any]
    vulnerability_contribution: dict[str, Any]
    uncertainty: dict[str, Any]
    data_quality: dict[str, Any]
    missing_data_limitations: tuple[str, ...]
    model_versions: dict[str, str]
    source_versions: dict[str, str]
    risk_level: str = "MODERATE"
    top_drivers: tuple[str, ...] = ()

    def validate(self) -> None:
        required = (
            self.rainfall_contribution,
            self.terrain_or_flood_contribution,
            self.exposure_contribution,
            self.vulnerability_contribution,
            self.uncertainty,
            self.data_quality,
            self.model_versions,
            self.source_versions,
        )
        if any(not value for value in required):
            raise ValueError("Every explanation component and provenance block is required")
        if self.uncertainty == self.data_quality:
            raise ValueError("Uncertainty and data quality must remain distinct concepts")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "risk_level": self.risk_level,
            "top_drivers": list(self.top_drivers),
            "components": {
                "rainfall": self.rainfall_contribution,
                "terrain_or_flood": self.terrain_or_flood_contribution,
                "exposure": self.exposure_contribution,
                "vulnerability": self.vulnerability_contribution,
            },
            "uncertainty": self.uncertainty,
            "data_quality": self.data_quality,
            "missing_data_limitations": list(self.missing_data_limitations),
            "model_versions": self.model_versions,
            "source_versions": self.source_versions,
            "causal_claim_disclaimer": "Component contributions reflect mathematical model associations, not proven physical causation.",
        }


def format_risk_explanation(explanation: RiskExplanation) -> str:
    explanation.validate()
    limitations = "; ".join(explanation.missing_data_limitations) or "none recorded"
    drivers = ", ".join(explanation.top_drivers) if explanation.top_drivers else "multi-factor interaction"
    return (
        f"Risk Level: {explanation.risk_level}. Top Drivers: {drivers}. "
        "Risk estimate components: "
        f"rainfall={explanation.rainfall_contribution}; "
        f"terrain/flood={explanation.terrain_or_flood_contribution}; "
        f"exposure={explanation.exposure_contribution}; "
        f"vulnerability={explanation.vulnerability_contribution}. "
        f"Uncertainty={explanation.uncertainty}. "
        f"Data quality={explanation.data_quality}. "
        f"Limitations: {limitations}. These are model contributions, not causal claims."
    )


class ExplainabilityEngine:
    """Derive decision-ready explanations from risk computation outputs."""

    @staticmethod
    def explain(
        risk_level: str,
        rainfall_value: float,
        susceptibility_value: float,
        exposure_value: float,
        vulnerability_value: float,
        *,
        uncertainty_info: dict[str, Any],
        data_quality_info: dict[str, Any],
        limitations: list[str] | tuple[str, ...],
        model_versions: dict[str, str],
        source_versions: dict[str, str],
    ) -> RiskExplanation:
        drivers: list[str] = []
        if rainfall_value > 30.0:
            drivers.append("high forecast rainfall intensity")
        elif rainfall_value > 15.0:
            drivers.append("moderate rainfall accumulation")

        if susceptibility_value > 0.6:
            drivers.append("high relative flood susceptibility / low elevation depression")

        if exposure_value > 0.5:
            drivers.append("high concentration of exposed assets")

        if vulnerability_value > 0.5:
            drivers.append("elevated structural or socioeconomic vulnerability")

        if not drivers:
            drivers.append("baseline low-hazard screening")

        exp = RiskExplanation(
            rainfall_contribution={"value_mm_h": rainfall_value, "weight": 0.4},
            terrain_or_flood_contribution={"susceptibility_score": susceptibility_value, "weight": 0.3},
            exposure_contribution={"score": exposure_value, "weight": 0.2},
            vulnerability_contribution={"score": vulnerability_value, "weight": 0.1},
            uncertainty=uncertainty_info,
            data_quality=data_quality_info,
            missing_data_limitations=tuple(limitations),
            model_versions=model_versions,
            source_versions=source_versions,
            risk_level=risk_level,
            top_drivers=tuple(drivers),
        )
        exp.validate()
        return exp
