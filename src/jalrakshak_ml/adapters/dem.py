from __future__ import annotations

import math
import os
from pathlib import Path

import rasterio
import tempfile
import urllib.request
import numpy as np
from rasterio.transform import Affine
from rasterio.session import AWSSession


def get_copernicus_dem_tile_names(bbox_wgs84: list[float]) -> list[str]:
    """Calculate the 1x1 degree Copernicus DEM 30m tile names required for a given WGS84 bbox."""
    west, south, east, north = bbox_wgs84
    min_lon = math.floor(west)
    max_lon = math.floor(east)
    min_lat = math.floor(south)
    max_lat = math.floor(north)

    tiles = []
    for lat in range(min_lat, max_lat + 1):
        for lon in range(min_lon, max_lon + 1):
            lat_str = f"N{lat:02d}" if lat >= 0 else f"S{-lat:02d}"
            lon_str = f"E{lon:03d}" if lon >= 0 else f"W{-lon:03d}"
            tile_name = f"Copernicus_DSM_COG_10_{lat_str}_00_{lon_str}_00_DEM"
            tiles.append(tile_name)
    return tiles


def numpy_merge(src_paths, bounds):
    minx, miny, maxx, maxy = bounds
    
    with rasterio.open(src_paths[0]) as src:
        res_x = src.transform[0]
        res_y = -src.transform[4]
        nodata = src.nodata if src.nodata is not None else -9999.0
    
    width = int(round((maxx - minx) / res_x))
    height = int(round((maxy - miny) / res_y))
    
    mosaic = np.full((1, height, width), nodata, dtype=np.float32)
    out_trans = Affine(res_x, 0.0, minx, 0.0, -res_y, maxy)
    
    for path in src_paths:
        with rasterio.open(path) as src:
            data = src.read(1)
            s_minx, s_miny, s_maxx, s_maxy = src.bounds
            
            i_minx = max(minx, s_minx)
            i_maxx = min(maxx, s_maxx)
            i_miny = max(miny, s_miny)
            i_maxy = min(maxy, s_maxy)
            
            if i_minx >= i_maxx or i_miny >= i_maxy:
                continue
                
            s_x_off = int(round((i_minx - s_minx) / res_x))
            s_y_off = int(round((s_maxy - i_maxy) / res_y))
            s_w = int(round((i_maxx - i_minx) / res_x))
            s_h = int(round((i_maxy - i_miny) / res_y))
            
            d_x_off = int(round((i_minx - minx) / res_x))
            d_y_off = int(round((maxy - i_maxy) / res_y))
            
            mosaic[0, d_y_off:d_y_off+s_h, d_x_off:d_x_off+s_w] = data[s_y_off:s_y_off+s_h, s_x_off:s_x_off+s_w]
            
    return mosaic, out_trans


class CopernicusDEMAdapter:
    """Adapter to fetch and merge Copernicus GLO-30 DEM from public AWS S3."""

    def __init__(self, bucket: str = "copernicus-dem-30m"):
        self.bucket = bucket
        self.source_name = "copernicus_glo_30"

    def fetch(self, bbox_wgs84: list[float], output_path: Path) -> Path:
        """
        Fetches the required 1x1 degree tiles via HTTP, merges them, crops to bbox, and saves to output_path.
        """
        tile_names = get_copernicus_dem_tile_names(bbox_wgs84)
        
        # HTTPS URIs for the public AWS bucket
        base_url = f"https://{self.bucket}.s3.amazonaws.com"
        tile_urls = [
            f"{base_url}/{name}/{name}.tif" for name in tile_names
        ]

        src_files_to_mosaic = []
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            for url, name in zip(tile_urls, tile_names):
                try:
                    print(f"Downloading {name}...")
                    local_path = tmp_path / f"{name}.tif"
                    urllib.request.urlretrieve(url, str(local_path))
                    src_files_to_mosaic.append(local_path)
                except Exception as e:
                    print(f"Warning: Could not download {url} - {e}")
            
            if not src_files_to_mosaic:
                raise RuntimeError("No DEM tiles could be downloaded for the specified bounding box.")

            # Pass file paths directly to numpy_merge
            src_paths = [str(p) for p in src_files_to_mosaic]
            print(f"Merging {len(src_paths)} tiles...")
            
            mosaic, out_trans = numpy_merge(src_paths, bounds=bbox_wgs84)
            
            with rasterio.open(src_paths[0]) as first_src:
                out_meta = first_src.meta.copy()

            out_meta.update({
                "driver": "GTiff",
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": out_trans,
                "compress": "deflate",
            })

            print("Saving merged DEM...")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(output_path, "w", **out_meta) as dest:
                dest.write(mosaic)
                
        return output_path
