from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import rasterio
import xarray as xr

from jalrakshak_ml.adapters.synthetic import SyntheticRainAdapter
from jalrakshak_ml.config import load_pilot_config
from jalrakshak_ml.preprocessing.grid import build_target_grid, reproject_array
from jalrakshak_ml.qc.weather import compute_quality_score, precipitation_qc
from jalrakshak_ml.schemas.weather import WeatherFrame
from jalrakshak_ml.utils.hashing import sha256_file


ROOT = Path.cwd()
RAW_DIR = ROOT / "data" / "raw" / "demo"
PROCESSED_DIR = ROOT / "data" / "processed" / "demo"


def _write_latest_geotiff(array: np.ndarray, grid: dict, path: Path) -> None:
    profile = {
        "driver": "GTiff",
        "height": grid["height"],
        "width": grid["width"],
        "count": 1,
        "dtype": "float32",
        "crs": grid["crs"],
        "transform": grid["transform"],
        "compress": "deflate",
        "tiled": True,
        "nodata": np.nan,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array.astype("float32"), 1)
        dst.set_band_description(1, "rainfall_rate_mm_h")


def main() -> None:
    pilot = load_pilot_config(ROOT / "configs" / "pilot" / "mumbai.yaml")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    adapter = SyntheticRainAdapter()
    raw = adapter.fetch(
        bbox_wgs84=pilot["bbox_wgs84"],
        steps=4,
        minutes_per_step=pilot["grid"]["temporal_step_minutes"],
        height=128,
        width=128,
    )

    raw_nc = RAW_DIR / "synthetic_rainfall.nc"
    raw.to_netcdf(raw_nc)

    target = build_target_grid(
        bbox_wgs84=pilot["bbox_wgs84"],
        analysis_crs=pilot["analysis_crs"],
        width=pilot["grid"]["width"],
        height=pilot["grid"]["height"],
    )

    processed_frames = []
    qcs = []

    for i in range(raw.sizes["time"]):
        src = raw["rainfall_rate"].isel(time=i).values
        qc = precipitation_qc(src)
        qcs.append(qc)

        dst = reproject_array(
            src,
            src_bounds_wgs84=pilot["bbox_wgs84"],
            dst_grid=target,
            continuous=True,
        )
        processed_frames.append(dst)

    processed = np.stack(processed_frames).astype("float32")

    left, bottom, right, top = target["bounds"]
    x = np.linspace(left + target["transform"].a / 2.0,
                    right - target["transform"].a / 2.0,
                    target["width"])
    pixel_h = abs(target["transform"].e)
    y = np.linspace(top - pixel_h / 2.0,
                    bottom + pixel_h / 2.0,
                    target["height"])

    ds = xr.Dataset(
        data_vars={
            "rainfall_rate": (("time", "y", "x"), processed)
        },
        coords={
            "time": raw["time"].values,
            "y": y,
            "x": x,
        },
        attrs={
            "pilot": pilot["name"],
            "crs": target["crs"],
            "api_crs": pilot["api_crs"],
            "units": "mm/h",
            "timezone": "UTC",
            "processing_version": "0.1.0",
        },
    )
    ds["rainfall_rate"].attrs["units"] = "mm/h"

    zarr_path = PROCESSED_DIR / "mumbai_rainfall.zarr"
    if zarr_path.exists():
        import shutil
        shutil.rmtree(zarr_path)
    ds.to_zarr(zarr_path, mode="w")

    tif_path = PROCESSED_DIR / "latest_rainfall.tif"
    _write_latest_geotiff(processed[-1], target, tif_path)

    latest_qc = qcs[-1]
    quality_score = compute_quality_score(
        completeness=latest_qc["completeness"],
        freshness=1.0,
        range_validity=latest_qc["range_validity"],
        spatial_coverage=latest_qc["completeness"],
        source_specific_qc=1.0,
    )

    valid_time_np = raw["time"].values[-1]
    valid_time = np.datetime_as_string(valid_time_np, unit="s") + "Z"

    manifest = WeatherFrame(
        source=adapter.source_name,
        variable="rainfall_rate",
        valid_time=datetime.fromisoformat(valid_time.replace("Z", "+00:00")),
        bbox=tuple(pilot["bbox_wgs84"]),
        crs=target["crs"],
        resolution_m=target["resolution_m"],
        units="mm/h",
        quality_score=quality_score,
        freshness_score=1.0,
        missing_percent=latest_qc["missing_percent"],
        object_uri=str(zarr_path.resolve()),
        checksum=sha256_file(tif_path),
        processing_version="0.1.0",
        provenance={
            "raw_uri": str(raw_nc.resolve()),
            "raw_checksum": sha256_file(raw_nc),
            "adapter": adapter.source_name,
            "transformations": [
                "synthetic source fixture",
                "range/missing-value QC",
                "EPSG:4326 -> EPSG:32643 reprojection",
                "bilinear resampling to 256x256 pilot grid",
            ],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    manifest_path = PROCESSED_DIR / "weatherframe_manifest.json"
    manifest_path.write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )

    grid_json = {
        "pilot": pilot["name"],
        "bbox_wgs84": pilot["bbox_wgs84"],
        "api_crs": pilot["api_crs"],
        "analysis_crs": pilot["analysis_crs"],
        "grid_width": target["width"],
        "grid_height": target["height"],
        "analysis_bounds": target["bounds"],
        "resolution_m": target["resolution_m"],
        "temporal_step_minutes": pilot["grid"]["temporal_step_minutes"],
    }
    (PROCESSED_DIR / "pilot_grid.json").write_text(
        json.dumps(grid_json, indent=2),
        encoding="utf-8",
    )

    print("JalRakshak Sprint-0 bootstrap complete.")
    print(f"Raw NetCDF:       {raw_nc}")
    print(f"Processed Zarr:   {zarr_path}")
    print(f"Latest GeoTIFF:   {tif_path}")
    print(f"Weather manifest: {manifest_path}")
    print(f"Quality score:    {quality_score:.3f}")
    print(f"Grid resolution:  ~{target['resolution_m']:.1f} m/cell")


if __name__ == "__main__":
    main()
