"""Geospatial exposure aggregation across canonical raster, H3, and vector assets.

Strictly uses genuine layers; never synthesizes population or building counts.
Distinguishes raw counts from normalized exposure scores.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np


class AssetClass(str, enum.Enum):
    POPULATION = "population"
    BUILDINGS = "buildings"
    ROADS = "roads"
    SCHOOLS = "schools"
    HOSPITALS = "hospitals"
    EMERGENCY_FACILITIES = "emergency_facilities"
    CRITICAL_INFRASTRUCTURE = "critical_infrastructure"
    TRANSPORT_ASSETS = "transport_assets"


@dataclass(frozen=True)
class ExposureAssetLayer:
    layer_id: str
    asset_class: AssetClass | str
    geometry_type: str  # raster, point, line, polygon
    crs: str
    source: str
    source_version: str
    source_sha256: str
    vintage: str
    raw_values: np.ndarray | None = None
    max_scale_value: float = 1.0
    license: str = "OpenStreetMap / Public"
    missingness_fraction: float = 0.0

    def validate(self) -> None:
        if not self.layer_id or not self.crs or not self.source:
            raise ValueError("Exposure layer requires valid id, CRS, and source")
        if len(self.source_sha256) != 64:
            raise ValueError("Exposure source SHA-256 is required")
        if self.raw_values is not None:
            if not np.isfinite(self.raw_values).all():
                raise ValueError("Exposure layer contains NaN or Inf")
            if (self.raw_values < 0).any():
                raise ValueError("Exposure layer values must be nonnegative")

    @property
    def normalized_values(self) -> np.ndarray | None:
        if self.raw_values is None:
            return None
        if self.max_scale_value <= 0:
            return np.zeros_like(self.raw_values, dtype=np.float32)
        norm = np.clip(self.raw_values / self.max_scale_value, 0.0, 1.0)
        return norm.astype(np.float32)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "asset_class": str(self.asset_class),
            "geometry_type": self.geometry_type,
            "crs": self.crs,
            "source": self.source,
            "source_version": self.source_version,
            "source_sha256": self.source_sha256,
            "vintage": self.vintage,
            "license": self.license,
            "missingness_fraction": self.missingness_fraction,
            "has_raw_values": self.raw_values is not None,
            "max_scale_value": self.max_scale_value,
        }


class AdvancedExposureEngine:
    """Geospatial exposure aggregation framework."""

    def __init__(self, canonical_crs: str = "EPSG:32643", grid_shape: tuple[int, int] = (256, 256)) -> None:
        self.canonical_crs = canonical_crs
        self.grid_shape = grid_shape

    def aggregate_raster_intersection(
        self,
        hazard: np.ndarray,
        layer: ExposureAssetLayer,
        hazard_threshold: float,
        hazard_crs: str,
    ) -> dict[str, Any]:
        layer.validate()
        if layer.raw_values is None:
            return {
                "status": "UNAVAILABLE",
                "layer_id": layer.layer_id,
                "reason": "Layer raw values are absent",
                "exposed_raw_sum": 0.0,
                "exposed_normalized_score": 0.0,
            }

        if layer.crs != hazard_crs or layer.raw_values.shape != hazard.shape:
            raise ValueError(
                f"Grid/CRS mismatch: Layer ({layer.crs}, {layer.raw_values.shape}) vs Hazard ({hazard_crs}, {hazard.shape})"
            )

        exposed_cells = hazard >= hazard_threshold
        raw_exposed = float(layer.raw_values[exposed_cells].sum())
        norm_values = layer.normalized_values
        norm_exposed = float(norm_values[exposed_cells].mean()) if exposed_cells.any() and norm_values is not None else 0.0

        return {
            "status": "AVAILABLE",
            "layer_id": layer.layer_id,
            "asset_class": str(layer.asset_class),
            "exposed_cell_count": int(np.count_nonzero(exposed_cells & (layer.raw_values > 0))),
            "exposed_raw_sum": raw_exposed,
            "exposed_normalized_score": float(np.clip(norm_exposed, 0.0, 1.0)),
            "provenance": layer.to_metadata(),
            "invented_counts": False,
        }

    def aggregate_h3(
        self,
        point_records: list[dict[str, Any]],
        indexer: Callable[[float, float], str],
    ) -> dict[str, dict[str, float]]:
        """Aggregate point features into H3 hex bins with raw count and normalized weight."""
        h3_bins: dict[str, float] = {}
        for rec in point_records:
            if "lat" not in rec or "lon" not in rec or "weight" not in rec:
                raise ValueError("Record requires lat, lon, and weight")
            cell = indexer(float(rec["lat"]), float(rec["lon"]))
            h3_bins[cell] = h3_bins.get(cell, 0.0) + float(rec["weight"])

        max_val = max(h3_bins.values()) if h3_bins else 1.0
        return {
            cell: {
                "raw_count": val,
                "normalized_score": float(val / max_val) if max_val > 0 else 0.0,
            }
            for cell, val in h3_bins.items()
        }
