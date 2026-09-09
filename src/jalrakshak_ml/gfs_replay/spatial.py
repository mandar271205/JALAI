"""Coordinate-derived GFS reprojection to the unchanged Mumbai pilot grid."""

from __future__ import annotations

import numpy as np
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

from .core import finite_rain


def canonicalize_grid(values, latitudes, longitudes):
    """Reorder regular lat/lon centers to north-up/east-right, wrapping 0..360."""
    arr = np.asarray(values, dtype=np.float64)
    lat = np.asarray(latitudes, dtype=np.float64)
    lon = (np.asarray(longitudes, dtype=np.float64) + 180) % 360 - 180
    if lat.ndim != 1 or lon.ndim != 1 or arr.shape != (len(lat), len(lon)):
        raise ValueError("Grid coordinates do not match array dimensions")
    if not np.isfinite(lat).all() or not np.isfinite(lon).all():
        raise ValueError("Non-finite grid coordinates")
    rows, cols = np.argsort(-lat), np.argsort(lon)
    lat, lon, arr = lat[rows], lon[cols], arr[np.ix_(rows, cols)]
    if len(lat) < 2 or len(lon) < 2:
        raise ValueError("Insufficient spatial coverage")
    if not np.allclose(np.diff(lat), -0.25) or not np.allclose(np.diff(lon), 0.25):
        raise ValueError("Expected regular 0.25-degree GFS grid; invalid orientation/coordinates")
    affine = from_origin(float(lon[0] - 0.125), float(lat[0] + 0.125), 0.25, 0.25)
    return arr, lat, lon, affine


def crop_with_halo(values, latitudes, longitudes, bbox, halo_cells=2):
    arr, lat, lon, _ = canonicalize_grid(values, latitudes, longitudes)
    west, south, east, north = bbox
    if halo_cells < 1 or not -180 < west < east < 180:
        raise ValueError("At least one halo cell and non-dateline-crossing bbox required")
    rows = np.flatnonzero((lat >= south - halo_cells * 0.25) & (lat <= north + halo_cells * 0.25))
    cols = np.flatnonzero((lon >= west - halo_cells * 0.25) & (lon <= east + halo_cells * 0.25))
    if len(rows) < 2 or len(cols) < 2:
        raise ValueError("Insufficient spatial coverage")
    if (
        lat[rows[0]] < north + 0.125
        or lat[rows[-1]] > south - 0.125
        or lon[cols[0]] > west - 0.125
        or lon[cols[-1]] < east + 0.125
    ):
        raise ValueError("Insufficient interpolation halo around target")
    return canonicalize_grid(arr[np.ix_(rows, cols)], lat[rows], lon[cols])


def reproject_rate(values, latitudes, longitudes, target_grid):
    """Use true source cell edges and the exact target affine; fail on missing output."""
    bbox = transform_bounds(target_grid["crs"], "EPSG:4326", *target_grid["bounds"], densify_pts=21)
    arr, _, _, affine = crop_with_halo(values, latitudes, longitudes, bbox)
    finite_rain(arr)
    output = np.full((target_grid["height"], target_grid["width"]), np.nan, dtype=np.float64)
    reproject(
        source=arr,
        destination=output,
        src_transform=affine,
        src_crs="EPSG:4326",
        src_nodata=np.nan,
        dst_transform=target_grid["transform"],
        dst_crs=target_grid["crs"],
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    finite_rain(output)
    metadata = {
        "source_crs": "EPSG:4326",
        "source_resolution_degrees": [0.25, 0.25],
        "source_resolution_note": "approximately 28 km; resampling creates no new detail",
        "source_affine": list(affine)[:6],
        "source_shape": list(arr.shape),
        "source_latitude_orientation": "descending_north_to_south",
        "source_longitude_convention": "-180_to_180_ascending",
        "halo_cells": 2,
        "resampling": "bilinear",
        "target_grid": {
            "crs": target_grid["crs"],
            "shape": list(output.shape),
            "affine": list(target_grid["transform"])[:6],
            "bounds": list(target_grid["bounds"]),
        },
    }
    return output, metadata


def reproject_field(
    values,
    latitudes,
    longitudes,
    target_grid: dict,
    *,
    physical_range: tuple[float, float] | None = None,
    variable_name: str = "field",
) -> tuple[np.ndarray, dict]:
    """Reproject general meteorological field to target grid using bilinear interpolation.

    Supports signed variables (e.g. u10/v10 wind components).
    Does NOT enforce non-negativity (finite_rain is NOT called).
    Validates finite values and physical bounds.
    """
    bbox = transform_bounds(target_grid["crs"], "EPSG:4326", *target_grid["bounds"], densify_pts=21)
    arr, _, _, affine = crop_with_halo(values, latitudes, longitudes, bbox)
    if not np.isfinite(arr).all():
        raise ValueError(f"Non-finite input values in {variable_name} or insufficient spatial coverage")
    if physical_range is not None:
        min_v, max_v = physical_range
        if np.any(arr < min_v) or np.any(arr > max_v):
            raise ValueError(
                f"Variable '{variable_name}' violates physical_range [{min_v}, {max_v}]: "
                f"observed [{np.nanmin(arr)}, {np.nanmax(arr)}]"
            )
    output = np.full((target_grid["height"], target_grid["width"]), np.nan, dtype=np.float64)
    reproject(
        source=arr,
        destination=output,
        src_transform=affine,
        src_crs="EPSG:4326",
        src_nodata=np.nan,
        dst_transform=target_grid["transform"],
        dst_crs=target_grid["crs"],
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    if not np.isfinite(output).all():
        raise ValueError(f"Non-finite output values after reprojecting {variable_name}")
    if physical_range is not None:
        min_v, max_v = physical_range
        if np.any(output < min_v) or np.any(output > max_v):
            raise ValueError(
                f"Variable '{variable_name}' violates physical_range [{min_v}, {max_v}] after reprojection: "
                f"observed [{np.nanmin(output)}, {np.nanmax(output)}]"
            )
    metadata = {
        "variable_name": variable_name,
        "source_crs": "EPSG:4326",
        "source_resolution_degrees": [0.25, 0.25],
        "source_resolution_note": "approximately 28 km; resampling creates no new detail",
        "source_affine": list(affine)[:6],
        "source_shape": list(arr.shape),
        "source_latitude_orientation": "descending_north_to_south",
        "source_longitude_convention": "-180_to_180_ascending",
        "halo_cells": 2,
        "resampling": "bilinear",
        "interpolation_method": "bilinear",
        "physical_range": list(physical_range) if physical_range else None,
        "target_grid": {
            "crs": target_grid["crs"],
            "shape": list(output.shape),
            "affine": list(target_grid["transform"])[:6],
            "bounds": list(target_grid["bounds"]),
        },
    }
    return output, metadata
