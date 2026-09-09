"""Relative flood-susceptibility contracts and executable geospatial pipeline.

Outputs are strictly relative susceptibility rankings; NEVER water depth.
"""

from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import numpy as np


class LayerPolicy(str, enum.Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    EXCLUDED = "EXCLUDED"


class SusceptibilityCategory(str, enum.Enum):
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


SUSCEPTIBILITY_CATEGORY_THRESHOLDS = (
    (0.2, SusceptibilityCategory.VERY_LOW),
    (0.4, SusceptibilityCategory.LOW),
    (0.6, SusceptibilityCategory.MODERATE),
    (0.8, SusceptibilityCategory.HIGH),
    (1.0, SusceptibilityCategory.VERY_HIGH),
)


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

    @property
    def resolution(self) -> tuple[float, float]:
        return (abs(self.transform[0]), abs(self.transform[4]))


@dataclass(frozen=True)
class SusceptibilityFeature:
    name: str
    values: np.ndarray
    grid: RasterGrid
    source: str
    source_sha256: str
    source_resolution: tuple[float, float] | None = None
    units: str = "dimensionless"
    preprocessing_method: str = "rank_percentile"
    timestamp_or_static: str = "static"

    def validate(self) -> None:
        if not self.name or not self.source or len(self.source_sha256) != 64:
            raise ValueError("Feature requires valid name, source, and 64-char SHA-256")
        self.grid.validate()
        if self.values.shape != (self.grid.height, self.grid.width):
            raise ValueError("Feature array shape does not match grid dimensions")


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
        valid_values = self.score[self.valid_mask]
        if valid_values.size > 0:
            if not np.isfinite(valid_values).all():
                raise ValueError("Susceptibility contains non-finite valid values")
            if (valid_values < 0.0).any() or (valid_values > 1.0).any():
                raise ValueError("Susceptibility score must be in [0, 1]")

    def refuse_depth_export(self, requested_units: str) -> None:
        if requested_units in {"m", "meter", "meters", "depth_m", "flood_depth", "inundation_depth"}:
            raise PermissionError("Susceptibility is not physics-derived water depth")

    @property
    def continuous_score(self) -> np.ndarray:
        return self.score

    @property
    def normalized_score(self) -> np.ndarray:
        return self.score

    def categorical_classes(self) -> np.ndarray:
        """Map continuous score [0, 1] into categorical susceptibility strings."""
        result = np.full(self.score.shape, "NODATA", dtype=object)
        if not self.valid_mask.any():
            return result
        valid = self.valid_mask
        scores = self.score[valid]
        categories = np.empty(scores.shape, dtype=object)
        categories[:] = SusceptibilityCategory.VERY_HIGH.value
        categories[scores < 0.8] = SusceptibilityCategory.HIGH.value
        categories[scores < 0.6] = SusceptibilityCategory.MODERATE.value
        categories[scores < 0.4] = SusceptibilityCategory.LOW.value
        categories[scores < 0.2] = SusceptibilityCategory.VERY_LOW.value
        result[valid] = categories
        return result

    def to_stac_metadata(self, item_id: str = "mumbai_susceptibility_v1") -> dict[str, Any]:
        """Produce a STAC-compatible metadata structure."""
        crs = self.metadata.get("crs", "EPSG:32643")
        return {
            "type": "Feature",
            "stac_version": "1.0.0",
            "id": item_id,
            "properties": {
                "title": "Mumbai Relative Flood Susceptibility",
                "description": "Deterministic multi-criteria topographic susceptibility (relative screening only, not depth)",
                "proj:epsg": int(crs.replace("EPSG:", "")) if crs.startswith("EPSG:") else crs,
                "proj:shape": list(self.score.shape),
                "proj:transform": self.metadata.get("transform"),
                "susceptibility:quantity": "relative_flood_susceptibility",
                "susceptibility:units": "dimensionless",
                "susceptibility:calibrated_depth": False,
                "susceptibility:features": self.metadata.get("feature_list", []),
                "susceptibility:weights": self.metadata.get("weights", {}),
                "susceptibility:source_provenance": self.metadata.get("provenance", {}),
            },
            "assets": {
                "raster": {
                    "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                    "roles": ["data", "susceptibility"],
                },
                "audit": {
                    "type": "application/json",
                    "roles": ["metadata", "audit"],
                },
            },
        }


def compute_slope(dem: np.ndarray, cell_size_x: float, cell_size_y: float) -> np.ndarray:
    """Compute terrain slope using central differences on 2D elevation raster."""
    if dem.ndim != 2 or min(dem.shape) < 2:
        raise ValueError("DEM must be a 2D array of at least 2x2 cells")
    if cell_size_x <= 0 or cell_size_y <= 0:
        raise ValueError("Cell sizes must be positive")
    dz_dy, dz_dx = np.gradient(dem, cell_size_y, cell_size_x)
    return np.sqrt(dz_dx**2 + dz_dy**2).astype(np.float32)


def compute_low_lying_index(dem: np.ndarray, kernel_radius: int = 5) -> np.ndarray:
    """Compute low-lying topographic depression index: relative elevation below neighborhood."""
    if dem.ndim != 2 or min(dem.shape) < 3:
        raise ValueError("DEM must be at least 3x3 cells")
    from scipy.ndimage import uniform_filter

    mean_elev = uniform_filter(dem.astype(np.float64), size=2 * kernel_radius + 1, mode="nearest")
    # Higher index = more depressed / lower than local neighborhood (higher susceptibility)
    low_lying = np.maximum(0.0, mean_elev - dem)
    return low_lying.astype(np.float32)


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
        *,
        layer_policies: dict[str, LayerPolicy | str] | None = None,
    ) -> SusceptibilityResult:
        if not features:
            raise ValueError("At least one genuine feature is required")

        # Validate policies if provided
        policies = {k: LayerPolicy(v) for k, v in (layer_policies or {}).items()}
        active_features = []
        for feat in features:
            pol = policies.get(feat.name, LayerPolicy.REQUIRED)
            if pol == LayerPolicy.EXCLUDED:
                continue
            active_features.append(feat)

        # Check required missing layers
        present_names = {f.name for f in active_features}
        for req_name, pol in policies.items():
            if pol == LayerPolicy.REQUIRED and req_name not in present_names:
                raise ValueError(f"Required susceptibility layer is missing: {req_name}")

        features = active_features
        if not features:
            raise ValueError("No active features remaining after applying layer policies")

        names = [feature.name for feature in features]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate feature names provided")
        if set(names) != set(weights):
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
            # Inverse ranking for elevation, slope, and distance_to_water
            # (lower elevation/slope/distance -> higher flood susceptibility)
            if feature.name in {"elevation", "slope", "distance_to_water"}:
                ranks = 1.0 - ranks
            layer = np.zeros(expected_shape, dtype=np.float64)
            layer[valid] = ranks
            total += weights[feature.name] * layer

        total /= sum(weights.values())
        total[~valid] = np.nan

        provenance = {}
        for feature in features:
            res = feature.source_resolution or reference.resolution
            provenance[feature.name] = {
                "source": feature.source,
                "sha256": feature.source_sha256,
                "source_resolution": list(res),
                "working_grid_resolution": list(reference.resolution),
                "units": feature.units,
                "preprocessing_method": feature.preprocessing_method,
                "timestamp_or_static": feature.timestamp_or_static,
            }

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
                "transform": list(reference.transform),
                "resolution": [reference.transform[0], abs(reference.transform[4])],
                "provenance": provenance,
                "calibrated_depth": False,
                "limitations": [
                    "Relative screening layer only",
                    "Not water depth, inundation probability, or hydraulic calibration",
                    "Assumes static topography without drainage capacity",
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
        "stac_item": result.to_stac_metadata(),
    }
    payload = json.dumps(metadata, sort_keys=True, allow_nan=False).encode()
    return {**metadata, "metadata_sha256": hashlib.sha256(payload).hexdigest()}
