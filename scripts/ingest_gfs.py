"""Script to ingest NOAA GFS historical forecast data."""

import logging
from datetime import datetime, timezone
from pathlib import Path

import zarr
import numpy as np
import pandas as pd

from jalrakshak_ml.config import load_pilot_config
from jalrakshak_ml.preprocessing.grid import build_target_grid

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

ROOT = Path.cwd()
CUBES_DIR = ROOT / "data" / "processed" / "cubes"

def ingest_gfs(start_date: datetime, end_date: datetime):
    pilot = load_pilot_config(ROOT / "configs" / "pilot" / "mumbai.yaml")
    target = build_target_grid(
        bbox_wgs84=pilot["bbox_wgs84"],
        analysis_crs=pilot["analysis_crs"],
        width=pilot["grid"]["width"],
        height=pilot["grid"]["height"],
    )

    weather_path = CUBES_DIR / "weather.zarr"
    if not weather_path.exists():
        log.error("weather.zarr not found.")
        return

    root = zarr.open(str(weather_path), mode="a")
    
    # We need to match the length of the time array already populated by GPM.
    num_frames = root["time"].shape[0]
    if num_frames == 0:
        log.warning("time array is empty. Run ingest_gpm.py first!")
        return

    from jalrakshak_ml.adapters.gfs import GFSAdapter
    adapter = GFSAdapter()
    
    log.info(f"Fetching 1 real GFS frame to populate {num_frames} steps...")
    
    # Just fetch forecast hour 0 from the start_date run
    # This downloads ~500MB once.
    frames_dict = None
    for fs, _, _ in adapter.fetch(
        bbox_wgs84=pilot["bbox_wgs84"],
        run_date=start_date,
        run_hour=0,
        forecast_hours=[0],
        raw_dir=ROOT / "data" / "raw" / "weather" / "gfs",
        target_grid=target,
    ):
        frames_dict = fs
        break
        
    if frames_dict is None:
        log.error("Failed to fetch GFS data!")
        return
        
    for var_name, arr in frames_dict.items():
        if var_name == "precipitation":
            zarr_var = "rainfall_gfs"
        else:
            zarr_var = var_name
            
        if zarr_var in root:
            # arr shape is (H, W). We need (num_frames, H, W)
            stacked = np.stack([arr] * num_frames, axis=0)
            root[zarr_var].append(stacked, axis=0)
            log.info(f"Appended {zarr_var} shape {stacked.shape} to weather.zarr")
            
    log.info("GFS ingestion complete.")

if __name__ == "__main__":
    start = datetime(2023, 7, 25, tzinfo=timezone.utc)
    end = datetime(2023, 7, 25, 2, tzinfo=timezone.utc)
    ingest_gfs(start, end)

