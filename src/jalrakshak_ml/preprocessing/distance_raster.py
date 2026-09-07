"""Distance raster computation.

Given a GeoDataFrame of vector features (lines or polygons),
burns them to the canonical 256×256 grid and computes Euclidean
distance in metres using scipy.ndimage.distance_transform_edt.

No bbox/CRS hardcoding — all spatial parameters come from the target grid dict.
"""
from __future__ import annotations

import numpy as np

try:
    from scipy.ndimage import distance_transform_edt
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False


def compute_distance_raster(
    gdf,   # geopandas.GeoDataFrame in the *analysis CRS* (e.g. EPSG:32643)
    target_grid: dict,
    resolution_m: float | None = None,
) -> np.ndarray:
    """
    Burn vector features into a binary raster then compute per-pixel
    Euclidean distance (metres) to the nearest feature.

    Parameters
    ----------
    gdf : GeoDataFrame in the same projected CRS as target_grid
    target_grid : dict from build_target_grid() with keys width/height/transform/crs
    resolution_m : override pixel resolution in metres (default: target_grid['resolution_m'])

    Returns
    -------
    distance : float32 ndarray of shape (height, width), values in metres
    """
    if not _SCIPY_AVAILABLE:
        raise ImportError("scipy is required for distance raster computation. "
                          "Install it with: conda install -c conda-forge scipy")

    from rasterio.features import rasterize
    from rasterio.transform import Affine

    height = target_grid["height"]
    width = target_grid["width"]
    transform: Affine = target_grid["transform"]
    res = resolution_m if resolution_m is not None else target_grid["resolution_m"]

    if len(gdf) == 0:
        # Return infinite distance (no features present)
        return np.full((height, width), np.inf, dtype=np.float32)

    # Burn features to binary raster (1 = feature present)
    shapes = ((geom.__geo_interface__, 1) for geom in gdf.geometry if geom is not None and not geom.is_empty)

    binary = rasterize(
        shapes=shapes,
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype="uint8",
        all_touched=True,
    )

    # Invert: 0 = feature pixels (zero distance), 1 = background
    inverted = (binary == 0).astype(np.uint8)

    # Distance transform: number of pixels to nearest zero-pixel
    dist_pixels = distance_transform_edt(inverted)

    # Convert pixels → metres
    dist_metres = (dist_pixels * res).astype(np.float32)
    return dist_metres
