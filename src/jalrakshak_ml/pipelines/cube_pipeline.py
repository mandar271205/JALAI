"""Canonical Data Cube assembly pipeline.

Produces two Zarr v3 stores:

  data/processed/cubes/static.zarr   — feature × y × x
    Static layers (no time dimension). Variables:
      elevation, slope, flow_accumulation, low_lying_index, distance_to_water

  data/processed/cubes/weather.zarr  — time × y × x  (per variable)
    Dynamic weather layers. Variables:
      rainfall_gpm, rainfall_gfs, temperature, humidity, wind_u, wind_v

Architecture
------------
- Static cube is assembled from processed TIF files (Step 6/7/8 outputs).
- Weather cube starts empty (will be populated by GPM/GFS pipeline runs).
- Static layers are NOT repeated at every timestep — kept separate to avoid
  unnecessary data duplication.
- All arrays are float32 with nodata=NaN.
- zarr v3 API is used throughout.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import zarr

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

ROOT = Path.cwd()
STATIC_DIR = ROOT / "data" / "processed" / "static"
CUBES_DIR = ROOT / "data" / "processed" / "cubes"

# Static layers to ingest (name → filename in STATIC_DIR)
_STATIC_LAYERS = {
    "elevation": "elevation.tif",
    "slope": "slope.tif",
    "flow_accumulation": "flow_accumulation.tif",
    "low_lying_index": "low_lying_index.tif",
    "distance_to_water": "distance_to_water.tif",
}

# Weather cube variable names (populated by GPM/GFS pipelines)
_WEATHER_VARIABLES = [
    "rainfall_gpm",
    "rainfall_gfs",
    "temperature",
    "humidity",
    "wind_u",
    "wind_v",
]

# Chunk shape for weather cube
_TIME_CHUNK = 24       # 24 half-hourly frames per chunk (~12 hours)
_SPATIAL_CHUNK = 64    # 64×64 spatial tiles


def _read_tif(path: Path) -> tuple[np.ndarray, dict]:
    """Read a GeoTIFF → (float32 array, metadata dict)."""
    with rasterio.open(path) as src:
        arr = src.read(1).astype(np.float32)
        meta = {
            "crs": str(src.crs),
            "transform": list(src.transform),
            "width": src.width,
            "height": src.height,
            "nodata": src.nodata,
        }
    return arr, meta


def build_static_cube(output_dir: Path, grid_meta: dict | None = None) -> zarr.Group:
    """
    Assemble static.zarr from processed GeoTIFF files.

    Parameters
    ----------
    output_dir : directory containing elevation.tif etc.
    grid_meta : optional metadata dict to store as cube attributes

    Returns
    -------
    zarr.Group  (the opened store)
    """
    store_path = CUBES_DIR / "static.zarr"
    CUBES_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Building static.zarr → %s", store_path)
    root = zarr.open(str(store_path), mode="w")

    available: list[str] = []
    metas: dict[str, dict] = {}

    for var_name, fname in _STATIC_LAYERS.items():
        tif_path = output_dir / fname
        if not tif_path.exists():
            log.warning("  [SKIP] %s not found at %s", var_name, tif_path)
            continue

        arr, meta = _read_tif(tif_path)
        z = root.create_array(
            name=var_name,
            shape=arr.shape,
            chunks=arr.shape,   # single chunk for static data
            dtype="float32",
        )
        z[:] = arr
        metas[var_name] = meta
        available.append(var_name)
        log.info("  [OK] %s: shape=%s, min=%.2f, max=%.2f",
                 var_name, arr.shape,
                 float(np.nanmin(arr)), float(np.nanmax(arr)))

    # Store cube metadata as attributes
    root.attrs.update({
        "cube_type": "static",
        "variables": available,
        "source_resolution": "~120m",
        "spatial_dimensions": "y × x",
        "nodata": float("nan"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "layer_metadata": metas,
        **(grid_meta or {}),
    })

    log.info("static.zarr complete: %d variables", len(available))
    return root


def build_weather_cube(
    height: int = 256,
    width: int = 256,
    initial_time_size: int = 0,
) -> zarr.Group:
    """
    Create an empty weather.zarr store with the correct schema.
    Actual data is appended by GPM/GFS pipeline runs.

    Dimensions: time × y × x
    Each weather variable is a separate Zarr array.

    Returns
    -------
    zarr.Group
    """
    store_path = CUBES_DIR / "weather.zarr"
    CUBES_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Building weather.zarr → %s", store_path)
    root = zarr.open(str(store_path), mode="w")

    for var_name in _WEATHER_VARIABLES:
        root.create_array(
            name=var_name,
            shape=(initial_time_size, height, width),
            chunks=(_TIME_CHUNK, _SPATIAL_CHUNK, _SPATIAL_CHUNK),
            dtype="float32",
        )
        log.info("  [CREATED] %s: shape=(0, %d, %d)", var_name, height, width)

    # Time coordinate — store as ISO8601 strings (append as data arrives)
    root.create_array(
        name="time",
        shape=(initial_time_size,),
        chunks=(_TIME_CHUNK,),
        dtype="str",   # zarr v3 string type for UTC ISO8601 timestamps
    )

    root.attrs.update({
        "cube_type": "weather",
        "variables": _WEATHER_VARIABLES,
        "time_coordinate": "time",
        "time_zone": "UTC",
        "spatial_dimensions": "time × y × x",
        "spatial_resolution": "~120m @ 256×256",
        "source_resolution_gpm": "0.1 deg (~11 km) — NOT street-level accuracy",
        "source_resolution_gfs": "0.25 deg (~28 km) — NOT street-level accuracy",
        "nodata": float("nan"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    log.info("weather.zarr schema created (empty, ready for data ingestion)")
    return root


def main() -> None:
    from jalrakshak_ml.config import load_pilot_config
    from jalrakshak_ml.preprocessing.grid import build_target_grid

    pilot = load_pilot_config(ROOT / "configs" / "pilot" / "mumbai.yaml")
    target = build_target_grid(
        bbox_wgs84=pilot["bbox_wgs84"],
        analysis_crs=pilot["analysis_crs"],
        width=pilot["grid"]["width"],
        height=pilot["grid"]["height"],
    )
    grid_meta = {
        "bbox_wgs84": pilot["bbox_wgs84"],
        "analysis_crs": pilot["analysis_crs"],
        "resolution_m": target["resolution_m"],
    }

    static_root = build_static_cube(STATIC_DIR, grid_meta=grid_meta)
    weather_root = build_weather_cube(
        height=pilot["grid"]["height"],
        width=pilot["grid"]["width"],
    )

    # Write cube manifest
    manifest = {
        "static_cube": str(CUBES_DIR / "static.zarr"),
        "weather_cube": str(CUBES_DIR / "weather.zarr"),
        "static_variables": list(_STATIC_LAYERS.keys()),
        "weather_variables": _WEATHER_VARIABLES,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "grid": grid_meta,
    }
    manifest_path = CUBES_DIR / "cube_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log.info("cube_manifest.json written.")
    log.info("Data cube pipeline complete.")


if __name__ == "__main__":
    main()
