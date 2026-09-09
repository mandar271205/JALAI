"""Machine- and human-readable flood-risk explanations without causal overclaiming."""

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


def format_risk_explanation(explanation: RiskExplanation) -> str:
    explanation.validate()
    limitations = "; ".join(explanation.missing_data_limitations) or "none recorded"
    return (
        "Risk estimate components: "
        f"rainfall={explanation.rainfall_contribution}; "
        f"terrain/flood={explanation.terrain_or_flood_contribution}; "
        f"exposure={explanation.exposure_contribution}; "
        f"vulnerability={explanation.vulnerability_contribution}. "
        f"Uncertainty={explanation.uncertainty}. "
        f"Data quality={explanation.data_quality}. "
        f"Limitations: {limitations}. These are model contributions, not causal claims."
    )
