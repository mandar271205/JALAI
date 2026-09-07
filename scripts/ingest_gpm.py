"""Script to ingest NASA GPM IMERG historical precipitation data."""

import logging
from datetime import datetime, timezone
from pathlib import Path

import zarr
import numpy as np

from jalrakshak_ml.config import load_pilot_config
from jalrakshak_ml.preprocessing.grid import build_target_grid
from jalrakshak_ml.adapters.gpm import GPMIMERGAdapter

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

ROOT = Path.cwd()
CUBES_DIR = ROOT / "data" / "processed" / "cubes"

def ingest_gpm(start_date: datetime, end_date: datetime):
    pilot = load_pilot_config(ROOT / "configs" / "pilot" / "mumbai.yaml")
    target = build_target_grid(
        bbox_wgs84=pilot["bbox_wgs84"],
        analysis_crs=pilot["analysis_crs"],
        width=pilot["grid"]["width"],
        height=pilot["grid"]["height"],
    )

    weather_path = CUBES_DIR / "weather.zarr"
    if not weather_path.exists():
        log.error("weather.zarr not found. Run cube_pipeline.py first.")
        return

    root = zarr.open(str(weather_path), mode="a")
    time_array = root["time"]
    gpm_array = root["rainfall_gpm"]

    adapter = GPMIMERGAdapter()
    
    # Track appended data
    frames = []
    timestamps = []

    log.info(f"Fetching GPM data from {start_date} to {end_date}...")
    for frame, manifest in adapter.fetch(
        bbox_wgs84=pilot["bbox_wgs84"],
        start_date=start_date,
        end_date=end_date,
        raw_dir=ROOT / "data" / "raw" / "weather" / "gpm",
        target_grid=target,
    ):
        frames.append(frame)
        timestamps.append(manifest.valid_time.isoformat())
        log.info(f"Ingested {manifest.valid_time.isoformat()} - shape {frame.shape}")

    if not frames:
        log.warning("No data ingested!")
        return

    frames = np.stack(frames, axis=0) # (T, H, W)
    
    # Append to Zarr
    gpm_array.append(frames, axis=0)
    time_array.append(np.array(timestamps, dtype=str), axis=0)
    
    log.info(f"Successfully appended {len(frames)} frames to weather.zarr")
    
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, type=str, help="Start date (YYYY-MM-DDTHH:MM:SS)")
    parser.add_argument("--end", required=True, type=str, help="End date (YYYY-MM-DDTHH:MM:SS)")
    args = parser.parse_args()
    
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    ingest_gpm(start, end)

