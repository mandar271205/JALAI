import zarr
import numpy as np
from pathlib import Path

CUBES_DIR = Path("data/processed/cubes")
weather_path = CUBES_DIR / "weather.zarr"

if weather_path.exists():
    root = zarr.open(str(weather_path), mode="a")
    times = root["time"][:]
    gpm = root["rainfall_gpm"][:]
    gfs = root["rainfall_gfs"][:]
    
    # Get unique times and sort them
    _, unique_indices = np.unique(times, return_index=True)
    unique_indices = np.sort(unique_indices)
    
    new_times = times[unique_indices]
    new_gpm = gpm[unique_indices]
    
    # Overwrite the datasets
    # Drop and recreate to handle size changes
    del root["time"]
    del root["rainfall_gpm"]
    
    root.array("time", new_times)
    root.array("rainfall_gpm", new_gpm)
    
    print(f"Cleaned weather.zarr. Old GPM shape: {gpm.shape}, New GPM shape: {new_gpm.shape}")
else:
    print("weather.zarr not found")
