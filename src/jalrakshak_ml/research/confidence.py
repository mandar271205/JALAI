"""Transparent multi-component confidence contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CompositeConfidence:
    data_quality: float | None
    model_confidence: float | None
    source_coverage: float | None
    freshness: float | None
    uncertainty: float | None
    physics_validity: float | None
    exposure_completeness: float | None
    vulnerability_completeness: float | None
    combined_summary: float | None = None
    combined_summary_type: str = "NOT_COMPUTED"

    def validate(self) -> None:
        values = asdict(self)
        for key, value in values.items():
            if key.endswith("type") or value is None:
                continue
            if not 0 <= value <= 1:
                raise ValueError(f"{key} must be in [0,1]")
        if self.combined_summary is not None and self.combined_summary_type not in {
            "HEURISTIC_NOT_CALIBRATED",
            "FORMALLY_CALIBRATED",
        }:
            raise ValueError("Combined confidence must declare its calibration status")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def with_heuristic_summary(cls, **components: float | None) -> CompositeConfidence:
        present = [value for value in components.values() if value is not None]
        summary = sum(present) / len(present) if present else None
        return cls(
            **components, combined_summary=summary, combined_summary_type="HEURISTIC_NOT_CALIBRATED"
        )
