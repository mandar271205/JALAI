"""Drainage and water network topology auditing and evidence manifest.

Evaluates genuine vector waterways, enforces topological QC, and strictly prevents
marking incomplete surface waterways as ready for 1D pipe hydraulic models (SWMM).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, MultiLineString, shape


@dataclass(frozen=True)
class DrainageEvidenceManifest:
    source: str
    source_path: str
    crs: str
    feature_count: int
    feature_types: dict[str, int]
    total_length_km: float
    bbox_wgs84: list[float]
    topology_qc: dict[str, Any]
    usable_for_susceptibility: bool = True
    usable_for_lisflood_fp: bool = True
    usable_for_swmm: bool = False
    swmm_blocker_reasons: list[str] = field(default_factory=list)
    completeness_caveat: str = (
        "OpenStreetMap waterways reflect crowdsourced surface channels only; "
        "they do NOT represent the subterranean municipal storm sewer pipe network of Mumbai."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DrainageAuditor:
    """Performs topological auditing on genuine vector drainage and water features."""

    def __init__(self, geojson_path: Path | str) -> None:
        self.path = Path(geojson_path)
        if not self.path.is_file():
            raise FileNotFoundError(f"Drainage vector file not found: {self.path}")

    def audit(self) -> DrainageEvidenceManifest:
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        feature_types: dict[str, int] = {}
        total_length_deg = 0.0

        endpoints: dict[tuple[float, float], int] = {}
        segment_hashes: set[tuple[tuple[float, float], tuple[float, float]]] = set()
        duplicate_segments = 0
        invalid_geometries = 0
        self_intersections = 0

        min_lon, min_lat = float("inf"), float("inf")
        max_lon, max_lat = float("-inf"), float("-inf")

        for feat in features:
            props = feat.get("properties", {}) or {}
            wtype = props.get("waterway") or "unclassified"
            feature_types[wtype] = feature_types.get(wtype, 0) + 1

            geom = feat.get("geometry")
            if not geom:
                invalid_geometries += 1
                continue

            try:
                geom_obj = shape(geom)
            except (ValueError, TypeError, KeyError):
                invalid_geometries += 1
                continue

            if not geom_obj.is_valid:
                invalid_geometries += 1
                geom_obj = geom_obj.buffer(0)

            if isinstance(geom_obj, (LineString, MultiLineString)):
                total_length_deg += geom_obj.length
                lines = [geom_obj] if isinstance(geom_obj, LineString) else list(geom_obj.geoms)

                for line in lines:
                    coords = list(line.coords)
                    if len(coords) < 2:
                        continue

                    # Bounding box calculation
                    for x, y in coords:
                        min_lon = min(min_lon, x)
                        max_lon = max(max_lon, x)
                        min_lat = min(min_lat, y)
                        max_lat = max(max_lat, y)

                    # Track endpoints for network connectivity
                    start_pt = (round(coords[0][0], 6), round(coords[0][1], 6))
                    end_pt = (round(coords[-1][0], 6), round(coords[-1][1], 6))
                    endpoints[start_pt] = endpoints.get(start_pt, 0) + 1
                    endpoints[end_pt] = endpoints.get(end_pt, 0) + 1

                    # Check duplicate segments
                    seg_key = (min(start_pt, end_pt), max(start_pt, end_pt))
                    if seg_key in segment_hashes:
                        duplicate_segments += 1
                    else:
                        segment_hashes.add(seg_key)

                    # Self-intersection check
                    if not line.is_simple:
                        self_intersections += 1

        # Calculate dangling edges (endpoints connected to only 1 line)
        dangling_nodes = sum(1 for count in endpoints.values() if count == 1)
        junction_nodes = sum(1 for count in endpoints.values() if count > 1)

        # Approximate length in km: 1 degree latitude ~ 111 km at 19 deg N
        approx_km = total_length_deg * 111.0

        swmm_blockers = [
            "Missing underground conduit geometries, dimensions, and materials",
            "Missing junction manhole rim elevations and invert depths",
            "Missing municipal stormwater outfall boundary tide flap conditions",
            "Missing subcatchment delineation and runoff routing connections",
            "Missing pipe slope and invert elevation consistency from surveyed records",
        ]

        topology_qc = {
            "total_endpoints": len(endpoints),
            "dangling_endpoints": dangling_nodes,
            "junction_nodes": junction_nodes,
            "duplicate_segments": duplicate_segments,
            "invalid_geometries": invalid_geometries,
            "self_intersecting_lines": self_intersections,
            "network_connectivity_ratio": float(junction_nodes / len(endpoints)) if endpoints else 0.0,
            "elevation_consistency": "UNKNOWN_NO_SURVEYED_INVERTS",
            "flow_direction_verified": False,
        }

        bbox_wgs84 = (
            [round(min_lon, 4), round(min_lat, 4), round(max_lon, 4), round(max_lat, 4)]
            if min_lon != float("inf")
            else [0.0, 0.0, 0.0, 0.0]
        )

        return DrainageEvidenceManifest(
            source="OpenStreetMap Waterways",
            source_path=str(self.path),
            crs="EPSG:4326",
            feature_count=len(features),
            feature_types=feature_types,
            total_length_km=round(approx_km, 2),
            bbox_wgs84=bbox_wgs84,
            topology_qc=topology_qc,
            usable_for_susceptibility=True,
            usable_for_lisflood_fp=True,
            usable_for_swmm=False,
            swmm_blocker_reasons=swmm_blockers,
        )
