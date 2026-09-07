from __future__ import annotations

import numpy as np
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds


def build_target_grid(
    bbox_wgs84: list[float],
    analysis_crs: str,
    width: int,
    height: int,
) -> dict:
    west, south, east, north = bbox_wgs84
    left, bottom, right, top = transform_bounds(
        "EPSG:4326", analysis_crs, west, south, east, north, densify_pts=21
    )
    transform = from_bounds(left, bottom, right, top, width=width, height=height)
    resolution_x = abs(transform.a)
    resolution_y = abs(transform.e)

    return {
        "crs": analysis_crs,
        "bounds": [left, bottom, right, top],
        "width": width,
        "height": height,
        "transform": transform,
        "resolution_m": float((resolution_x + resolution_y) / 2.0),
    }


def reproject_array(
    source: np.ndarray,
    *,
    src_bounds_wgs84: list[float],
    dst_grid: dict,
    continuous: bool = True,
    src_nodata: float | None = None,
    dst_nodata: float = np.nan,
) -> np.ndarray:
    """Reproject one 2-D source frame from EPSG:4326 to the pilot grid."""
    src = np.asarray(source, dtype="float32")
    if src.ndim != 2:
        raise ValueError("source must be 2-D.")

    west, south, east, north = src_bounds_wgs84
    src_transform = from_bounds(west, south, east, north, src.shape[1], src.shape[0])

    dst = np.full(
        (dst_grid["height"], dst_grid["width"]),
        dst_nodata,
        dtype="float32",
    )

    reproject(
        source=src,
        destination=dst,
        src_transform=src_transform,
        src_crs="EPSG:4326",
        src_nodata=src_nodata,
        dst_transform=dst_grid["transform"],
        dst_crs=dst_grid["crs"],
        dst_nodata=dst_nodata,
        resampling=Resampling.bilinear if continuous else Resampling.nearest,
    )
    return dst
