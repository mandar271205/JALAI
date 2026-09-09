"""Relative flood-susceptibility contracts; these outputs are never water depth."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import numpy as np


@dataclass(frozen=True)
class RasterGrid:
    crs: str
    width: int
    height: int
    transform: tuple[float, float, float, float, float, float]

    def validate(self) -> None:
        if not self.crs.startswith("EPSG:") or self.width < 1 or self.height < 1:
            raise ValueError("A valid projected grid is required")
        if len(self.transform) != 6:
            raise ValueError("Affine transform must contain six values")


@dataclass(frozen=True)
class SusceptibilityFeature:
    name: str
    values: np.ndarray
    grid: RasterGrid
    source: str
    source_sha256: str


@dataclass(frozen=True)
class SusceptibilityResult:
    score: np.ndarray
    valid_mask: np.ndarray
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        if self.metadata.get("quantity") != "relative_flood_susceptibility":
            raise ValueError("Susceptibility quantity label is required")
        if self.metadata.get("units") != "dimensionless" or self.metadata.get("calibrated_depth"):
            raise ValueError("Relative susceptibility cannot be represented as water depth")
        if not np.isfinite(self.score[self.valid_mask]).all():
            raise ValueError("Susceptibility contains non-finite valid values")
        if ((self.score[self.valid_mask] < 0) | (self.score[self.valid_mask] > 1)).any():
            raise ValueError("Susceptibility score must be in [0, 1]")

    def refuse_depth_export(self, requested_units: str) -> None:
        if requested_units in {"m", "meter", "meters", "depth_m"}:
            raise PermissionError("Susceptibility is not physics-derived water depth")


class FloodSusceptibilityEngine:
    """Transparent weighted-rank susceptibility from genuine aligned features."""

    version = "relative_susceptibility_v1"
    supported_features: ClassVar[set[str]] = {
        "elevation",
        "slope",
        "flow_accumulation",
        "low_lying_index",
        "distance_to_water",
        "imperviousness",
    }

    def score(
        self,
        features: list[SusceptibilityFeature],
        weights: dict[str, float],
    ) -> SusceptibilityResult:
        if not features:
            raise ValueError("At least one genuine feature is required")
        names = [feature.name for feature in features]
        if len(names) != len(set(names)) or set(names) != set(weights):
            raise ValueError("Feature names and explicit weights must match exactly")
        if not set(names).issubset(self.supported_features):
            raise ValueError("Unsupported or fabricated susceptibility feature")
        reference = features[0].grid
        reference.validate()
        if any(feature.grid != reference for feature in features):
            raise ValueError("All susceptibility rasters must share CRS/grid/transform")
        expected_shape = (reference.height, reference.width)
        if any(feature.values.shape != expected_shape for feature in features):
            raise ValueError("Feature raster shape does not match declared grid")
        if any(not feature.source or len(feature.source_sha256) != 64 for feature in features):
            raise ValueError("Every feature requires source provenance and SHA-256")
        if any(weight < 0 for weight in weights.values()) or sum(weights.values()) <= 0:
            raise ValueError("Weights must be nonnegative with a positive total")

        valid = np.logical_and.reduce([np.isfinite(feature.values) for feature in features])
        if not valid.any():
            raise ValueError("No common valid feature cells")
        total = np.zeros(expected_shape, dtype=np.float64)
        for feature in features:
            values = feature.values[valid].astype(np.float64)
            order = np.argsort(np.argsort(values, kind="stable"), kind="stable")
            ranks = order / max(1, len(values) - 1)
            if feature.name in {"elevation", "slope", "distance_to_water"}:
                ranks = 1.0 - ranks
            layer = np.zeros(expected_shape, dtype=np.float64)
            layer[valid] = ranks
            total += weights[feature.name] * layer
        total /= sum(weights.values())
        total[~valid] = np.nan
        return SusceptibilityResult(
            total.astype(np.float32),
            valid,
            {
                "method_version": self.version,
                "quantity": "relative_flood_susceptibility",
                "units": "dimensionless",
                "feature_list": names,
                "weights": weights,
                "crs": reference.crs,
                "resolution": [reference.transform[0], abs(reference.transform[4])],
                "provenance": {
                    feature.name: {
                        "source": feature.source,
                        "sha256": feature.source_sha256,
                    }
                    for feature in features
                },
                "calibrated_depth": False,
                "limitations": [
                    "Relative screening layer only",
                    "Not water depth, inundation probability, or hydraulic calibration",
                ],
            },
        )


def susceptibility_cog_schema(result: SusceptibilityResult, path: str | Path) -> dict[str, Any]:
    """Return the immutable metadata sidecar contract for a future COG writer."""
    result.refuse_depth_export("depth_m") if result.metadata.get(
        "units"
    ) != "dimensionless" else None
    metadata = {
        **result.metadata,
        "artifact_type": "cloud_optimized_geotiff",
        "path": str(path),
        "dtype": "float32",
        "nodata": "NaN",
    }
    payload = json.dumps(metadata, sort_keys=True, allow_nan=False).encode()
    return {**metadata, "metadata_sha256": hashlib.sha256(payload).hexdigest()}
