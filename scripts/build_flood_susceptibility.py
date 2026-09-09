"""Build reproducible relative flood susceptibility raster and STAC/GeoTIFF metadata.

Outputs are strictly relative susceptibility rankings; NEVER water depth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio

from jalrakshak_ml.flood.susceptibility import (
    FloodSusceptibilityEngine,
    LayerPolicy,
    RasterGrid,
    SusceptibilityFeature,
    susceptibility_cog_schema,
)

DEFAULT_WEIGHTS = {
    "elevation": 0.30,
    "slope": 0.25,
    "low_lying_index": 0.25,
    "distance_to_water": 0.20,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_susceptibility_from_static(
    static_dir: Path,
    output_tif: Path,
    output_audit: Path,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    weights = weights or DEFAULT_WEIGHTS
    static_dir = Path(static_dir)

    elevation_tif = static_dir / "elevation.tif"
    if not elevation_tif.is_file():
        raise FileNotFoundError(f"Required elevation raster not found in {static_dir}")

    with rasterio.open(elevation_tif) as src:
        crs_str = str(src.crs)
        t = src.transform
        transform_tuple = (t.a, t.b, t.c, t.d, t.e, t.f)
        shape = src.shape

    grid = RasterGrid(crs_str, shape[1], shape[0], transform_tuple)
    grid.validate()

    feature_map = {
        "elevation": (static_dir / "elevation.tif", "copernicus_glo_30"),
        "slope": (static_dir / "slope.tif", "derived_copernicus_slope"),
        "low_lying_index": (static_dir / "low_lying_index.tif", "derived_topographic_depression"),
        "distance_to_water": (static_dir / "distance_to_water.tif", "osm_derived_water_distance"),
        "flow_accumulation": (static_dir / "flow_accumulation.tif", "derived_d8_accumulation"),
    }

    features: list[SusceptibilityFeature] = []
    layer_policies: dict[str, LayerPolicy] = {}

    for feat_name in weights:
        if feat_name not in feature_map:
            raise ValueError(f"Unknown susceptibility feature: {feat_name}")
        file_path, source_name = feature_map[feat_name]
        if not file_path.is_file():
            raise FileNotFoundError(f"Feature raster {feat_name} not found at {file_path}")

        with rasterio.open(file_path) as src:
            arr = src.read(1).astype(np.float32)
            if arr.shape != shape:
                raise ValueError(f"Feature {feat_name} shape {arr.shape} does not match DEM {shape}")

        feat = SusceptibilityFeature(
            name=feat_name,
            values=arr,
            grid=grid,
            source=source_name,
            source_sha256=_sha256(file_path),
            source_resolution=grid.resolution,
        )
        features.append(feat)
        layer_policies[feat_name] = LayerPolicy.REQUIRED

    engine = FloodSusceptibilityEngine()
    result = engine.score(features, weights, layer_policies=layer_policies)

    # Save output GeoTIFF
    output_tif.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        output_tif,
        "w",
        driver="GTiff",
        height=shape[0],
        width=shape[1],
        count=1,
        dtype=rasterio.float32,
        crs=crs_str,
        transform=t,
        nodata=np.nan,
    ) as dst:
        dst.write(result.score, 1)

    # Produce metadata & audit
    schema_metadata = susceptibility_cog_schema(result, output_tif)
    categorical = result.categorical_classes()
    cat_counts = {}
    for cat in ("VERY_LOW", "LOW", "MODERATE", "HIGH", "VERY_HIGH"):
        cat_counts[cat] = int(np.count_nonzero(categorical == cat))

    audit_payload = {
        "status": "PASS",
        "output_tif": str(output_tif),
        "shape": list(shape),
        "crs": crs_str,
        "valid_cells": int(np.count_nonzero(result.valid_mask)),
        "total_cells": int(result.valid_mask.size),
        "categorical_distribution": cat_counts,
        "weights": weights,
        "metadata": schema_metadata,
        "susceptibility_is_not_depth": True,
        "calibrated_depth": False,
    }

    output_audit.parent.mkdir(parents=True, exist_ok=True)
    output_audit.write_text(json.dumps(audit_payload, indent=2), encoding="utf-8")
    return audit_payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--static-dir",
        type=Path,
        default=Path("data/processed/static"),
        help="Directory containing genuine static terrain rasters",
    )
    parser.add_argument(
        "--output-tif",
        type=Path,
        default=Path("data/processed/flood/susceptibility_v1.tif"),
        help="Output GeoTIFF path",
    )
    parser.add_argument(
        "--output-audit",
        type=Path,
        default=Path("reports/phase5_susceptibility_audit.json"),
        help="Output audit JSON path",
    )
    args = parser.parse_args()

    audit = build_susceptibility_from_static(
        args.static_dir,
        args.output_tif,
        args.output_audit,
    )
    print(f"Susceptibility build successful. Valid cells: {audit['valid_cells']}/{audit['total_cells']}")
    print(f"Audit written to: {args.output_audit}")


if __name__ == "__main__":
    main()
