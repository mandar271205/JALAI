"""Exposure, vulnerability, probabilistic risk, and uncertainty contracts."""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np


class RiskCategory(str, enum.Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


@dataclass(frozen=True)
class ExposureLayer:
    layer_id: str
    asset_type: str
    geometry_type: str
    crs: str
    source: str
    source_version: str
    source_sha256: str
    values: np.ndarray | None = None

    def validate(self) -> None:
        if not all((self.layer_id, self.asset_type, self.crs, self.source, self.source_version)):
            raise ValueError("Exposure identity and provenance are required")
        if len(self.source_sha256) != 64:
            raise ValueError("Exposure source SHA-256 is required")
        if self.values is not None and not np.isfinite(self.values).all():
            raise ValueError("Exposure contains NaN or Inf")


class ExposureEngine:
    """Intersect genuine aligned asset layers with hazard; never synthesize counts."""

    def intersect_raster(
        self,
        hazard: np.ndarray,
        layer: ExposureLayer,
        *,
        hazard_crs: str,
        threshold: float,
    ) -> dict[str, Any]:
        layer.validate()
        if layer.values is None:
            return {"status": "UNAVAILABLE", "reason": "source values absent"}
        if layer.crs != hazard_crs or layer.values.shape != hazard.shape:
            raise ValueError("Exposure and hazard must be explicitly aligned in CRS and grid")
        exposed = hazard >= threshold
        return {
            "status": "AVAILABLE",
            "asset_type": layer.asset_type,
            "exposed_cell_count": int(np.count_nonzero(exposed & (layer.values > 0))),
            "exposed_weight": float(layer.values[exposed].sum()),
            "provenance": {
                "source": layer.source,
                "source_version": layer.source_version,
                "sha256": layer.source_sha256,
            },
            "invented_counts": False,
        }

    def aggregate_h3(
        self,
        records: list[dict[str, Any]],
        indexer: Callable[[float, float], str],
    ) -> dict[str, float]:
        output: dict[str, float] = {}
        for record in records:
            if not all(key in record for key in ("lat", "lon", "weight")):
                raise ValueError("H3 exposure records require genuine coordinates and weights")
            cell = indexer(float(record["lat"]), float(record["lon"]))
            output[cell] = output.get(cell, 0.0) + float(record["weight"])
        return output


@dataclass(frozen=True)
class VulnerabilityFactor:
    name: str
    value: float | None
    units: str
    source: str | None
    uncertainty: tuple[float, float] | None = None

    def validate(self) -> None:
        if self.value is None:
            return
        if not 0.0 <= self.value <= 1.0 or not self.source:
            raise ValueError("Vulnerability factor must be normalized and sourced")
        if self.uncertainty is not None:
            low, high = self.uncertainty
            if not 0.0 <= low <= self.value <= high <= 1.0:
                raise ValueError("Invalid vulnerability uncertainty interval")


@dataclass(frozen=True)
class VulnerabilityCurve:
    hazard_values: tuple[float, ...]
    damage_fractions: tuple[float, ...]
    source: str
    version: str

    def evaluate(self, hazard: np.ndarray) -> np.ndarray:
        if len(self.hazard_values) != len(self.damage_fractions) or len(self.hazard_values) < 2:
            raise ValueError("Vulnerability curve is malformed")
        if any(a >= b for a, b in zip(self.hazard_values, self.hazard_values[1:], strict=False)):
            raise ValueError("Hazard values must increase")
        if any(value < 0 or value > 1 for value in self.damage_fractions) or not self.source:
            raise ValueError("Damage fractions must be sourced and in [0,1]")
        return np.interp(hazard, self.hazard_values, self.damage_fractions)


def vulnerability_status(factors: list[VulnerabilityFactor]) -> dict[str, Any]:
    for factor in factors:
        factor.validate()
    missing = [factor.name for factor in factors if factor.value is None]
    return {
        "status": "PARTIAL" if missing else "AVAILABLE",
        "missing_factors": missing,
        "factors": [factor.__dict__ for factor in factors],
    }


@dataclass(frozen=True)
class RiskMethodology:
    version: str
    hazard_scale: tuple[float, float]
    exposure_scale: tuple[float, float]
    vulnerability_scale: tuple[float, float] = (0.0, 1.0)
    category_boundaries: tuple[float, float, float] = (0.2, 0.5, 0.8)

    @staticmethod
    def _scale(value: float, bounds: tuple[float, float]) -> float:
        low, high = bounds
        if high <= low:
            raise ValueError("Risk normalization scale is invalid")
        return float(np.clip((value - low) / (high - low), 0.0, 1.0))

    def evaluate(
        self,
        *,
        hazard: float,
        exposure: float,
        vulnerability: float,
        provenance: dict[str, Any],
        data_quality: str,
        model_confidence: float | None,
        probability: float | None = None,
    ) -> dict[str, Any]:
        if not provenance or not 0 <= vulnerability <= 1:
            raise ValueError("Sourced, normalized vulnerability is required")
        h = self._scale(hazard, self.hazard_scale)
        e = self._scale(exposure, self.exposure_scale)
        v = self._scale(vulnerability, self.vulnerability_scale)
        raw = h * e * v
        boundaries = self.category_boundaries
        category = (
            RiskCategory.LOW.value
            if raw < boundaries[0]
            else RiskCategory.MODERATE.value
            if raw < boundaries[1]
            else RiskCategory.HIGH.value
            if raw < boundaries[2]
            else RiskCategory.SEVERE.value
        )
        return {
            "methodology_version": self.version,
            "raw_risk_score": raw,
            "normalized_risk_score": raw,
            "risk_category": category,
            "risk_probability": probability,
            "components": {"hazard": h, "exposure": e, "vulnerability": v},
            "data_quality": data_quality,
            "model_confidence": model_confidence,
            "provenance": provenance,
            "limitations": ["Scores depend on explicitly configured normalization scales"],
        }


class ProbabilisticHEVRiskEngine:
    """Computes spatial and ensemble H x E x V flood risk with uncertainty awareness."""

    def __init__(self, methodology: RiskMethodology) -> None:
        self.methodology = methodology

    def compute_spatial_risk(
        self,
        hazard_grid: np.ndarray,
        exposure_grid: np.ndarray,
        vulnerability_grid: np.ndarray,
        *,
        valid_mask: np.ndarray,
        data_quality: str,
        model_confidence: float | None,
    ) -> dict[str, Any]:
        if hazard_grid.shape != exposure_grid.shape or exposure_grid.shape != vulnerability_grid.shape:
            raise ValueError("Hazard, exposure, and vulnerability grids must share shape")

        h_low, h_high = self.methodology.hazard_scale
        e_low, e_high = self.methodology.exposure_scale
        v_low, v_high = self.methodology.vulnerability_scale

        h_norm = np.clip((hazard_grid - h_low) / max(1e-6, h_high - h_low), 0.0, 1.0)
        e_norm = np.clip((exposure_grid - e_low) / max(1e-6, e_high - e_low), 0.0, 1.0)
        v_norm = np.clip((vulnerability_grid - v_low) / max(1e-6, v_high - v_low), 0.0, 1.0)

        risk_continuous = h_norm * e_norm * v_norm
        risk_continuous[~valid_mask] = np.nan

        # Categorize
        b = self.methodology.category_boundaries
        cat_array = np.full(risk_continuous.shape, "NODATA", dtype=object)
        cat_array[valid_mask & (risk_continuous < b[0])] = RiskCategory.LOW.value
        cat_array[valid_mask & (risk_continuous >= b[0]) & (risk_continuous < b[1])] = RiskCategory.MODERATE.value
        cat_array[valid_mask & (risk_continuous >= b[1]) & (risk_continuous < b[2])] = RiskCategory.HIGH.value
        cat_array[valid_mask & (risk_continuous >= b[2])] = RiskCategory.SEVERE.value

        return {
            "risk_score": risk_continuous.astype(np.float32),
            "risk_categories": cat_array,
            "components": {
                "hazard_normalized": h_norm.astype(np.float32),
                "exposure_normalized": e_norm.astype(np.float32),
                "vulnerability_normalized": v_norm.astype(np.float32),
            },
            "valid_mask": valid_mask,
            "data_quality": data_quality,
            "model_confidence": model_confidence,
        }


def propagate_scenarios(
    scenario_values: list[np.ndarray] | np.ndarray,
    scenario_weights: list[float] | np.ndarray,
    *,
    calibrated_probabilities: bool | None = None,
    calibrated: bool | None = None,
    source: str = "unspecified",
) -> dict[str, Any]:
    if calibrated_probabilities is None:
        calibrated_probabilities = bool(calibrated)
    if len(scenario_values) == 0 or len(scenario_values) != len(scenario_weights):
        raise ValueError("Scenario values and weights must be nonempty and aligned")
    if any(value.shape != scenario_values[0].shape for value in scenario_values):
        raise ValueError("Scenario grids must align")
    weights = np.asarray(scenario_weights, dtype=float)
    if (weights < 0).any() or not np.isclose(weights.sum(), 1.0):
        raise ValueError("Scenario weights must be nonnegative and sum to one")
    stack = np.stack(scenario_values)
    mean = np.tensordot(weights, stack, axes=(0, 0))
    variance = np.tensordot(weights, (stack - mean) ** 2, axes=(0, 0))
    return {
        "expected": mean,
        "spread_standard_deviation": np.sqrt(variance),
        "scenario_count": len(scenario_values),
        "probability_calibrated": calibrated_probabilities,
        "probability_claim_allowed": calibrated_probabilities,
        "calibrated_probability": calibrated_probabilities,
        "source": source,
    }
