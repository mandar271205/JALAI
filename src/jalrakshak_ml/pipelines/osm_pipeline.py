"""OSM geospatial context pipeline.

Orchestrates:
  1. OSMAdapter.fetch() → raw GeoJSONs in data/raw/osm/
  2. Copy processed GeoJSONs to data/processed/static/
  3. Compute distance_to_water.tif on the canonical 256×256 grid
  4. Emit osm_manifest.json

No bbox or CRS is hardcoded here — all spatial parameters come from
the Mumbai pilot config.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import rasterio

from jalrakshak_ml.adapters.osm import OSMAdapter
from jalrakshak_ml.config import load_pilot_config
from jalrakshak_ml.preprocessing.distance_raster import compute_distance_raster
from jalrakshak_ml.preprocessing.grid import build_target_grid
from jalrakshak_ml.utils.hashing import sha256_file

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

ROOT = Path.cwd()
RAW_DIR = ROOT / "data" / "raw" / "osm"
STATIC_DIR = ROOT / "data" / "processed" / "static"

# Layers to copy as-is to static/
_COPY_LAYERS = [
    "roads", "waterways", "railways",
    "hospitals", "schools",
    "emergency_assets",
]


def write_geotiff(array, grid: dict, path: Path, nodata: float = 0.0) -> None:
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
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    pilot = load_pilot_config(ROOT / "configs" / "pilot" / "mumbai.yaml")
    bbox = pilot["bbox_wgs84"]

    # Build analysis grid (same canonical grid as DEM pipeline)
    target = build_target_grid(
        bbox_wgs84=bbox,
        analysis_crs=pilot["analysis_crs"],
        width=pilot["grid"]["width"],
        height=pilot["grid"]["height"],
    )

    # ── Fetch OSM data ────────────────────────────────────────────────────
    log.info("Starting OSM fetch for bbox %s", bbox)
    adapter = OSMAdapter()
    layers = adapter.fetch(bbox_wgs84=bbox, raw_dir=RAW_DIR)

    # ── Copy layers to processed/static/ ─────────────────────────────────
    feature_counts: dict[str, int] = {}
    processed_files: dict[str, str] = {}

    for layer_name in _COPY_LAYERS:
        raw_path = RAW_DIR / f"{layer_name}.geojson"
        if not raw_path.exists():
            log.warning("Layer %s not available — skipping.", layer_name)
            continue
        dst_path = STATIC_DIR / f"{layer_name}.geojson"
        shutil.copy2(raw_path, dst_path)
        try:
            gdf = gpd.read_file(str(dst_path))
            feature_counts[layer_name] = len(gdf)
        except Exception:
            feature_counts[layer_name] = -1
        processed_files[layer_name] = str(dst_path.relative_to(ROOT))
        log.info("Copied %s → %s", raw_path.name, dst_path.name)

    # ── distance_to_water.tif ─────────────────────────────────────────────
    dist_water_path = STATIC_DIR / "distance_to_water.tif"
    if "waterways" in layers and len(layers["waterways"]) > 0:
        log.info("Computing distance_to_water raster...")
        # Reproject waterways to analysis CRS for accurate metric distance
        waterways_proj = layers["waterways"].to_crs(pilot["analysis_crs"])
        dist_water = compute_distance_raster(waterways_proj, target)
        write_geotiff(dist_water, target, dist_water_path, nodata=0.0)
        log.info("distance_to_water.tif written (max=%.1f m)", float(dist_water.max()))
        feature_counts["distance_to_water"] = int(dist_water.size)
    else:
        log.warning("No waterways available — distance_to_water.tif skipped.")

    # ── OSM manifest ──────────────────────────────────────────────────────
    manifest = {
        "source": adapter.source_name,
        "acquisition_timestamp": datetime.now(timezone.utc).isoformat(),
        "processing_version": "0.1.0",
        "bbox_wgs84": bbox,
        "analysis_crs": pilot["analysis_crs"],
        "grid": {"width": target["width"], "height": target["height"]},
        "layers": processed_files,
        "feature_counts": feature_counts,
    }

    # Add checksums for static GeoJSONs
    checksums: dict[str, str] = {}
    for layer_name in _COPY_LAYERS:
        fpath = STATIC_DIR / f"{layer_name}.geojson"
        if fpath.exists():
            checksums[layer_name] = sha256_file(fpath)
    if dist_water_path.exists():
        checksums["distance_to_water"] = sha256_file(dist_water_path)
    manifest["checksums"] = checksums

    manifest_path = STATIC_DIR / "osm_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log.info("osm_manifest.json written.")
    log.info("OSM pipeline complete. Outputs: %s", STATIC_DIR)


if __name__ == "__main__":
    main()
