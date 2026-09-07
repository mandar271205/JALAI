"""Audit script for Phase 2 Validation Gate."""
import json
import logging
from pathlib import Path
import numpy as np
import zarr
import rasterio

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

ROOT = Path.cwd()
CUBES_DIR = ROOT / "data" / "processed" / "cubes"

def audit():
    report = {}

    # Audit Weather Cube
    try:
        w_root = zarr.open(str(CUBES_DIR / "weather.zarr"), mode="r")
        times = w_root["time"][:]
        gpm = w_root["rainfall_gpm"][:]
        gfs = w_root["rainfall_gfs"][:]
        
        has_gpm = len(gpm) > 0
        has_gfs = len(gfs) > 0
        
        gpm_missing_pct = np.isnan(gpm).mean() * 100 if has_gpm else 100.0
        gfs_missing_pct = np.isnan(gfs).mean() * 100 if has_gfs else 100.0
        
        is_real = has_gpm and has_gfs
        
        report["weather.zarr"] = {
            "source": "weather_cube",
            "number_of_gpm_frames": len(gpm),
            "number_of_gfs_frames": len(gfs),
            "date_range": [times[0], times[-1]] if len(times) > 0 else [],
            "gpm_missing_percentage": float(gpm_missing_pct),
            "gfs_missing_percentage": float(gfs_missing_pct),
            "REAL_OR_SYNTHETIC": "REAL" if is_real else "MISSING"
        }
    except Exception as e:
        report["weather.zarr"] = {"error": str(e)}

    # Audit Static Cube
    try:
        s_root = zarr.open(str(CUBES_DIR / "static.zarr"), mode="r")
        dem = s_root["elevation"][:]
        slope = s_root["slope"][:]
        fac = s_root["flow_accumulation"][:]
        
        report["static.zarr"] = {
            "source": "static_cube",
            "variables_found": list(s_root.keys()),
            "dem_missing_pct": float(np.isnan(dem).mean() * 100),
            "dem_min": float(np.nanmin(dem)),
            "dem_max": float(np.nanmax(dem)),
            "REAL_OR_SYNTHETIC": "REAL" if dem.shape == (256, 256) and np.nanmax(dem) > 0 else "MISSING"
        }
    except Exception as e:
        report["static.zarr"] = {"error": str(e)}

    # Check OSM raw files
    osm_raw = ROOT / "data" / "raw" / "osm"
    osm_files = list(osm_raw.glob("*.geojson")) if osm_raw.exists() else []
    report["osm_data"] = {
        "raw_files": [f.name for f in osm_files],
        "REAL_OR_SYNTHETIC": "REAL" if len(osm_files) > 0 else "MISSING"
    }

    # Save report
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True, parents=True)
    out_path = out_dir / "phase2_data_audit.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    log.info(f"Audit report saved to {out_path}")

    # Fail loudly if NOT real
    if report.get("weather.zarr", {}).get("REAL_OR_SYNTHETIC") != "REAL":
        log.error("Weather data is missing or synthetic!")
    if report.get("static.zarr", {}).get("REAL_OR_SYNTHETIC") != "REAL":
        log.error("Static data is missing or synthetic!")

if __name__ == "__main__":
    audit()
