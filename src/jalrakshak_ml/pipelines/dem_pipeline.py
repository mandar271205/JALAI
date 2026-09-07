from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio

from jalrakshak_ml.adapters.dem import CopernicusDEMAdapter
from jalrakshak_ml.config import load_pilot_config
from jalrakshak_ml.preprocessing.grid import build_target_grid, reproject_array
from jalrakshak_ml.preprocessing.terrain import (
    compute_d8_flow_direction,
    compute_flow_accumulation,
    compute_low_lying_index,
    compute_slope,
)
from jalrakshak_ml.utils.hashing import sha256_file

ROOT = Path.cwd()
RAW_DIR = ROOT / "data" / "raw" / "dem"
STATIC_DIR = ROOT / "data" / "processed" / "static"


def write_geotiff(array: np.ndarray, grid: dict, path: Path, nodata: float = np.nan) -> None:
    profile = {
        "driver": "GTiff",
        "height": grid["height"],
        "width": grid["width"],
        "count": 1,
        "dtype": str(array.dtype),
        "crs": grid["crs"],
        "transform": grid["transform"],
        "compress": "deflate",
        "tiled": True,
        "nodata": nodata,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array, 1)


def main() -> None:
    print("Starting Copernicus DEM Pipeline...")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    pilot = load_pilot_config(ROOT / "configs" / "pilot" / "mumbai.yaml")
    adapter = CopernicusDEMAdapter()

    raw_path = RAW_DIR / "copernicus_raw.tif"
    print(f"Fetching DEM for bbox {pilot['bbox_wgs84']}...")
    adapter.fetch(pilot["bbox_wgs84"], raw_path)

    print("Building target grid...")
    target = build_target_grid(
        bbox_wgs84=pilot["bbox_wgs84"],
        analysis_crs=pilot["analysis_crs"],
        width=pilot["grid"]["width"],
        height=pilot["grid"]["height"],
    )

    print("Reprojecting DEM...")
    with rasterio.open(raw_path) as src:
        # Read the raw bounds and array for reprojection
        raw_bounds = list(src.bounds)
        raw_array = src.read(1)
        raw_nodata = src.nodata

    # Reproject to pilot grid
    elevation = reproject_array(
        raw_array,
        src_bounds_wgs84=raw_bounds,
        dst_grid=target,
        continuous=True,
        src_nodata=raw_nodata,
        dst_nodata=np.nan,
    )

    elev_tif_path = STATIC_DIR / "elevation.tif"
    elev_npy_path = STATIC_DIR / "elevation.npy"
    write_geotiff(elevation, target, elev_tif_path)
    np.save(elev_npy_path, elevation)
    
    print("Computing terrain features...")
    slope = compute_slope(elevation, target["resolution_m"])
    flow_dir = compute_d8_flow_direction(elevation)
    flow_acc = compute_flow_accumulation(flow_dir, elevation)
    lli = compute_low_lying_index(elevation, flow_acc)

    write_geotiff(slope, target, STATIC_DIR / "slope.tif")
    write_geotiff(flow_acc, target, STATIC_DIR / "flow_accumulation.tif")
    write_geotiff(lli, target, STATIC_DIR / "low_lying_index.tif")

    print("Generating manifests...")
    generated_at = datetime.now(timezone.utc).isoformat()
    
    dem_manifest = {
        "source": adapter.source_name,
        "bbox": pilot["bbox_wgs84"],
        "source_crs": "EPSG:4326",
        "target_crs": target["crs"],
        "resolution_m": target["resolution_m"],
        "checksum": sha256_file(elev_tif_path),
        "acquisition_timestamp": generated_at,
        "processing_version": "0.1.0",
        "transformations": [
            "Fetch COP30 1x1 degree tiles",
            "Mosaic tiles",
            f"Reproject EPSG:4326 -> {target['crs']}",
            f"Bilinear resample to {target['width']}x{target['height']}"
        ]
    }
    (STATIC_DIR / "dem_manifest.json").write_text(json.dumps(dem_manifest, indent=2))

    terrain_manifest = {
        "source_elevation_checksum": sha256_file(elev_tif_path),
        "target_crs": target["crs"],
        "resolution_m": target["resolution_m"],
        "processing_version": "0.1.0",
        "features_generated": [
            "slope",
            "flow_direction_d8",
            "flow_accumulation",
            "low_lying_index"
        ],
        "generated_at": generated_at
    }
    (STATIC_DIR / "terrain_manifest.json").write_text(json.dumps(terrain_manifest, indent=2))

    print(f"Pipeline complete. Outputs saved to {STATIC_DIR}")


if __name__ == "__main__":
    main()
