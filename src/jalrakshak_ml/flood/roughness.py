"""Manning's n surface roughness engine and land-cover mapping.

Enforces strict physical constraints:
1. Categorical resampling must use nearest-neighbor/mode, never bilinear.
2. Roughness values must satisfy 0.010 <= n <= 0.200.
3. Calibration state defaults to UNCALIBRATED (literature-based engineering parameterization).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

# Literature-derived Manning's n parameterization for ESA WorldCover 11 classes
# Sources: Chow (1959) 'Open-Channel Hydraulics', Arcement & Schneider (1989) USGS WSP 2339
ESA_WORLDCOVER_CLASSES: dict[int, dict[str, Any]] = {
    10: {
        "meaning": "Tree cover",
        "manning_n": 0.120,
        "citation": "Chow (1959) Table 5-6: Dense forest floodplain with heavy timber and underbrush",
    },
    20: {
        "meaning": "Shrubland",
        "manning_n": 0.070,
        "citation": "Chow (1959) Table 5-6: Medium to dense brush, scattered bushes",
    },
    30: {
        "meaning": "Grassland",
        "manning_n": 0.035,
        "citation": "Chow (1959) Table 5-6: Pasture, short grass without brush",
    },
    40: {
        "meaning": "Cropland",
        "manning_n": 0.040,
        "citation": "Chow (1959) Table 5-6: Mature row crops, cultivated farmland",
    },
    50: {
        "meaning": "Built-up",
        "manning_n": 0.018,
        "citation": "FEMA Flood Insurance Study Guidelines: Paved asphalt/concrete urban surfaces",
    },
    60: {
        "meaning": "Bare / sparse vegetation",
        "manning_n": 0.030,
        "citation": "Chow (1959) Table 5-6: Smooth bare earth, graded ground, gravelly surface",
    },
    70: {
        "meaning": "Snow and ice",
        "manning_n": 0.015,
        "citation": "Chow (1959): Smooth ice sheet over water/rock",
    },
    80: {
        "meaning": "Permanent water bodies",
        "manning_n": 0.030,
        "citation": "Chow (1959) Table 5-6: Clean, regular natural stream channel",
    },
    90: {
        "meaning": "Herbaceous wetland",
        "manning_n": 0.080,
        "citation": "Arcement & Schneider (1989): Dense standing emergent marsh vegetation",
    },
    95: {
        "meaning": "Mangroves",
        "manning_n": 0.140,
        "citation": "Arcement & Schneider (1989): Dense mangrove stilt root entanglement in tidal flats",
    },
    100: {
        "meaning": "Moss and lichen",
        "manning_n": 0.030,
        "citation": "Chow (1959): Low tundra ground cover",
    },
}

ROUGHNESS_MIN_N = 0.010
ROUGHNESS_MAX_N = 0.200


@dataclass(frozen=True)
class RoughnessMetadata:
    calibration_state: str = "UNCALIBRATED"
    methodology: str = "literature_lookup_table"
    literature_basis: str = "Chow (1959) / Arcement & Schneider (1989) USGS WSP 2339"
    min_n: float = ROUGHNESS_MIN_N
    max_n: float = ROUGHNESS_MAX_N
    units: str = "s / m^(1/3)"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ManningRoughnessMapper:
    """Validates and maps land-cover and surface features to Manning's n roughness grids."""

    def __init__(self, metadata: RoughnessMetadata | None = None) -> None:
        self.metadata = metadata or RoughnessMetadata()

    @staticmethod
    def validate_resampling_method(method: str) -> None:
        """Reject continuous/interpolated resampling for categorical land-cover classes."""
        forbidden = {"bilinear", "cubic", "cubicspline", "lanczos", "linear", "average"}
        if method.lower() in forbidden:
            raise ValueError(
                f"Categorical land-cover classes cannot be resampled using '{method}'. "
                "Must use 'nearest' or 'mode' to avoid creating non-existent fractional class IDs."
            )

    @staticmethod
    def validate_roughness_values(roughness_grid: np.ndarray) -> None:
        """Enforce strict physical plausibility bounds on Manning's n."""
        if not np.isfinite(roughness_grid).all():
            raise ValueError("Roughness grid contains NaN or Infinite values")
        if (roughness_grid < ROUGHNESS_MIN_N).any():
            min_val = float(roughness_grid.min())
            raise ValueError(
                f"Roughness value {min_val:.4f} is below physical minimum {ROUGHNESS_MIN_N} s/m^(1/3)"
            )
        if (roughness_grid > ROUGHNESS_MAX_N).any():
            max_val = float(roughness_grid.max())
            raise ValueError(
                f"Roughness value {max_val:.4f} exceeds physical maximum {ROUGHNESS_MAX_N} s/m^(1/3)"
            )

    def map_worldcover_to_manning(
        self, landcover_grid: np.ndarray, nodata_val: int = 0
    ) -> np.ndarray:
        """Map discrete 2D ESA WorldCover integer classes to continuous Manning's n array."""
        roughness = np.full(landcover_grid.shape, 0.040, dtype=np.float32)  # default terrain

        for class_id, info in ESA_WORLDCOVER_CLASSES.items():
            mask = landcover_grid == class_id
            roughness[mask] = info["manning_n"]

        # Default for unclassified or nodata land areas
        nodata_mask = (landcover_grid == nodata_val) | (landcover_grid < 0)
        roughness[nodata_mask] = 0.040

        self.validate_roughness_values(roughness)
        return roughness

    def build_composite_roughness_from_features(
        self,
        grid_shape: tuple[int, int] = (256, 256),
        road_mask: np.ndarray | None = None,
        railway_mask: np.ndarray | None = None,
        waterway_mask: np.ndarray | None = None,
        default_terrain_n: float = 0.040,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """Build a deterministic surface roughness field from genuine local infrastructure overlays.
        
        Assumptions:
        - Roads (asphalt/concrete): n = 0.015
        - Railways (ballast/steel): n = 0.025
        - Waterways (open stream/drain): n = 0.035
        - General terrain (mixed suburban/open): n = 0.040
        """
        roughness = np.full(grid_shape, default_terrain_n, dtype=np.float32)

        if railway_mask is not None and railway_mask.any():
            roughness[railway_mask] = 0.025
        if road_mask is not None and road_mask.any():
            roughness[road_mask] = 0.015
        if waterway_mask is not None and waterway_mask.any():
            roughness[waterway_mask] = 0.035

        self.validate_roughness_values(roughness)

        assumptions = {
            "calibration_state": self.metadata.calibration_state,
            "units": self.metadata.units,
            "bounds": [ROUGHNESS_MIN_N, ROUGHNESS_MAX_N],
            "feature_parameters": {
                "roads_asphalt": 0.015,
                "railways_ballast": 0.025,
                "waterways_channel": 0.035,
                "default_terrain_mixed": default_terrain_n,
            },
            "literature_basis": self.metadata.literature_basis,
            "note": "Engineering parameterization; not empirically calibrated to discharge gauge records.",
        }

        return roughness, assumptions
