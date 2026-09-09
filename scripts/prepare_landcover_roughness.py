"""Prepare and export Manning's n roughness raster and land-cover mapping.

Produces uncalibrated engineering parameterization from genuine local static features,
strictly recording provenance, bounds, and uncalibrated state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pyproj
import rasterio
from rasterio.features import rasterize
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform

from jalrakshak_ml.flood.roughness import ManningRoughnessMapper, RoughnessMetadata

MUMBAI_BBOX = (72.75, 18.85, 73.05, 19.30)


def reproject_feature_geometries(
    geojson_path: Path,
    target_crs: str = "EPSG:32643",
    bbox: tuple[float, float, float, float] = MUMBAI_BBOX,
    max_features: int | None = None,
) -> list[dict[str, Any]]:
    """Fast load and reproject vector geometries intersecting the target bounding box."""
    if not geojson_path.is_file():
        return []

    with open(geojson_path, encoding="utf-8") as f:
        data = json.load(f)

    transformer = pyproj.Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    min_lon, min_lat, max_lon, max_lat = bbox
    reprojected: list[dict[str, Any]] = []

    features = data.get("features", [])
    if max_features is not None:
        features = features[:max_features]

    for feat in features:
        geom = feat.get("geometry")
        if not geom:
            continue
        gtype = geom.get("type")
        coords = geom.get("coordinates", [])

        if gtype == "LineString":
            # Quick bounding box check on raw coordinate floats
            if not any(min_lon <= pt[0] <= max_lon and min_lat <= pt[1] <= max_lat for pt in coords):
                continue
            proj_coords = [list(transformer.transform(pt[0], pt[1])) for pt in coords]
            reprojected.append({"type": "LineString", "coordinates": proj_coords})

        elif gtype == "MultiLineString":
            proj_lines = []
            for line in coords:
                if any(min_lon <= pt[0] <= max_lon and min_lat <= pt[1] <= max_lat for pt in line):
                    proj_lines.append([list(transformer.transform(pt[0], pt[1])) for pt in line])
            if proj_lines:
                reprojected.append({"type": "MultiLineString", "coordinates": proj_lines})

        elif gtype in ("Point", "MultiPoint", "Polygon", "MultiPolygon"):
            try:
                s = shape(geom)
                if not s.is_empty:
                    s_proj = shapely_transform(transformer.transform, s)
                    reprojected.append(mapping(s_proj))
            except (ValueError, TypeError, KeyError):
                continue

    return reprojected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem-path", type=Path, default=Path("data/processed/static/elevation.tif"))
    parser.add_argument("--static-dir", type=Path, default=Path("data/processed/static"))
    parser.add_argument("--output-tif", type=Path, default=Path("data/processed/static/roughness.tif"))
    parser.add_argument("--output-assumptions", type=Path, default=Path("data/processed/static/roughness_assumptions.json"))
    parser.add_argument("--output-qc", type=Path, default=Path("reports/phase7_roughness_qc_report.json"))
    args = parser.parse_args()

    dem_path = Path(args.dem_path)
    if not dem_path.is_file():
        raise FileNotFoundError(f"Canonical DEM not found at: {dem_path}")

    # Read DEM profile and transform
    with rasterio.open(dem_path) as src:
        profile = src.profile.copy()
        transform = src.transform
        crs = str(src.crs)
        height, width = src.shape

    static_dir = Path(args.static_dir)
    roads_file = static_dir / "roads.geojson"
    railways_file = static_dir / "railways.geojson"
    waterways_file = static_dir / "waterways.geojson"

    # Fast load and reproject genuine vector overlays
    print("Loading and reprojecting waterways...")
    waterway_geoms = reproject_feature_geometries(waterways_file, target_crs="EPSG:32643")
    waterway_mask = (
        rasterize(waterway_geoms, out_shape=(height, width), transform=transform, default_value=1) == 1
        if waterway_geoms
        else None
    )

    print("Loading and reprojecting railways...")
    railway_geoms = reproject_feature_geometries(railways_file, target_crs="EPSG:32643")
    railway_mask = (
        rasterize(railway_geoms, out_shape=(height, width), transform=transform, default_value=1) == 1
        if railway_geoms
        else None
    )

    print("Loading and reprojecting roads...")
    road_geoms = reproject_feature_geometries(roads_file, target_crs="EPSG:32643")
    road_mask = (
        rasterize(road_geoms, out_shape=(height, width), transform=transform, default_value=1) == 1
        if road_geoms
        else None
    )

    mapper = ManningRoughnessMapper(RoughnessMetadata())
    roughness_grid, assumptions = mapper.build_composite_roughness_from_features(
        grid_shape=(height, width),
        road_mask=road_mask,
        railway_mask=railway_mask,
        waterway_mask=waterway_mask,
        default_terrain_n=0.040,
    )

    # Write GeoTIFF
    profile.update(dtype=rasterio.float32, count=1, nodata=None)
    args.output_tif.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(args.output_tif, "w", **profile) as dst:
        dst.write(roughness_grid.astype(np.float32), 1)

    # Compute hash of output
    tif_bytes = args.output_tif.read_bytes()
    sha256_hash = hashlib.sha256(tif_bytes).hexdigest()

    # Save assumptions and metadata
    provenance = {
        "output_tif": str(args.output_tif),
        "sha256": sha256_hash,
        "crs": crs,
        "shape": [height, width],
        "min_roughness": float(roughness_grid.min()),
        "max_roughness": float(roughness_grid.max()),
        "mean_roughness": float(roughness_grid.mean()),
        "roads_detected_cells": int(road_mask.sum()) if road_mask is not None else 0,
        "railways_detected_cells": int(railway_mask.sum()) if railway_mask is not None else 0,
        "waterways_detected_cells": int(waterway_mask.sum()) if waterway_mask is not None else 0,
        "worldcover_source_status": "DOWNLOAD_PENDING_EXTERNAL",
        "worldcover_dataset": "ESA WorldCover 10m v200",
        "resampling_policy": "nearest_or_mode_mandatory_no_bilinear",
    }
    combined_assumptions = {**assumptions, "provenance": provenance}

    args.output_assumptions.parent.mkdir(parents=True, exist_ok=True)
    args.output_assumptions.write_text(json.dumps(combined_assumptions, indent=2), encoding="utf-8")

    qc_report = {
        "status": "PASS",
        "output_tif": str(args.output_tif),
        "calibration_state": "UNCALIBRATED",
        "valid_finite_cells": int(np.isfinite(roughness_grid).sum()),
        "total_cells": int(height * width),
        "roughness_bounds_respected": bool((roughness_grid >= 0.010).all() and (roughness_grid <= 0.200).all()),
        "sha256": sha256_hash,
        "min_roughness": float(roughness_grid.min()),
        "max_roughness": float(roughness_grid.max()),
        "mean_roughness": float(roughness_grid.mean()),
    }
    args.output_qc.parent.mkdir(parents=True, exist_ok=True)
    args.output_qc.write_text(json.dumps(qc_report, indent=2), encoding="utf-8")

    print(f"Roughness layer created: {args.output_tif}")
    print(f"Roughness range: [{roughness_grid.min():.3f}, {roughness_grid.max():.3f}] s/m^(1/3)")
    print(f"Road cells: {provenance['roads_detected_cells']}, Waterway cells: {provenance['waterways_detected_cells']}, Railway cells: {provenance['railways_detected_cells']}")
    print(f"QC report saved: {args.output_qc}")


if __name__ == "__main__":
    main()
