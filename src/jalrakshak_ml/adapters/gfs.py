"""NOAA GFS (Global Forecast System) NWP adapter.

Source: NOAA NOMADS public HTTPS server — no authentication required.
        GRIB2 files, 0.25° global grid, 6-hourly model runs (00/06/12/18Z),
        forecast hours 000–384.

Variables fetched:
  - APCP  : Accumulated precipitation (mm)  → rainfall (mm/h equivalent)
  - TMP   : Temperature at 2m               (K)
  - RH    : Relative humidity at 2m         (%)
  - UGRD  : U-component wind at 10m         (m/s)
  - VGRD  : V-component wind at 10m         (m/s)

⚠ RESOLUTION NOTE:
   GFS native resolution is 0.25° (~28 km at the equator). After bilinear
   resampling to the 256×256 Mumbai canonical grid (~120 m), the data remains
   coarse GFS resolution — it must NOT be presented or used as street-level
   data. The original 0.25° resolution is preserved in every WeatherFrame manifest.

Architecture: No GFS-specific logic leaks beyond this module. The pipeline
receives canonical numpy arrays and WeatherFrame manifests.
"""
from __future__ import annotations

import logging
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import numpy as np

from jalrakshak_ml.preprocessing.grid import reproject_array
from jalrakshak_ml.qc.frame_qc import FrameQC
from jalrakshak_ml.schemas.weather_frame import WeatherFrame

log = logging.getLogger(__name__)

_SOURCE_RESOLUTION = "0.25 deg (~28 km)"
_PROCESSING_VERSION = "0.2.0"

# AWS S3 PDS URL template for GFS 0p25
# https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.YYYYMMDD/HH/atmos/
_NOMADS_BASE = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"

# cfgrib filter_by_keys for each variable
_GFS_VARIABLES = {
    "temperature": {
        "typeOfLevel": "heightAboveGround",
        "level": 2,
        "shortName": "2t",
        "units": "K",
        "canonical_units": "K",
    },
    "humidity": {
        "typeOfLevel": "heightAboveGround",
        "level": 2,
        "shortName": "2r",
        "units": "%",
        "canonical_units": "%",
    },
    "wind_u": {
        "typeOfLevel": "heightAboveGround",
        "level": 10,
        "shortName": "10u",
        "units": "m/s",
        "canonical_units": "m/s",
    },
    "wind_v": {
        "typeOfLevel": "heightAboveGround",
        "level": 10,
        "shortName": "10v",
        "units": "m/s",
        "canonical_units": "m/s",
    },
    "precipitation": {
        "typeOfLevel": "surface",
        "shortName": "tp",
        "units": "mm",
        "canonical_units": "mm",
    },
}


class GFSAdapter:
    """
    Fetch, QC, and reproject NOAA GFS 0.25° forecast data.

    Usage
    -----
    adapter = GFSAdapter()
    for frames, manifests, valid_time in adapter.fetch(
            bbox_wgs84=[72.75, 18.85, 73.05, 19.30],
            run_date=datetime(2024, 8, 15, tzinfo=timezone.utc),
            run_hour=0,
            forecast_hours=[1, 2, 3, 6, 12, 24],
            raw_dir=Path("data/raw/gfs"),
            target_grid=grid,
    ):
        # frames: dict[variable_name -> np.ndarray (256, 256)]
        # manifests: dict[variable_name -> WeatherFrame]
    """

    source_name = "gfs_0p25"

    def __init__(self):
        self._qc_seen: set[str] = set()

    def fetch(
        self,
        bbox_wgs84: list[float],
        run_date: datetime,
        run_hour: int,           # 0, 6, 12, or 18
        forecast_hours: list[int],
        raw_dir: Path,
        target_grid: dict,
    ) -> Iterator[tuple[dict[str, np.ndarray], dict[str, WeatherFrame], datetime]]:
        """
        Yield (variable_arrays, manifests, valid_time) for each forecast hour.

        Parameters
        ----------
        run_date : UTC date of the model run
        run_hour : model initialisation hour (0/6/12/18)
        forecast_hours : list of lead times to fetch (e.g. [1,2,3,6,12])
        """
        raw_dir.mkdir(parents=True, exist_ok=True)

        canonical_res = (
            f"~{target_grid['resolution_m']:.0f}m @ "
            f"{target_grid['width']}x{target_grid['height']}"
        )

        for fhr in sorted(forecast_hours):
            try:
                raw_path = self._download_grib2(run_date, run_hour, fhr, raw_dir)
                variable_arrays = self._parse_grib2(raw_path, bbox_wgs84)
                valid_dt = datetime(
                    run_date.year, run_date.month, run_date.day,
                    run_hour, tzinfo=timezone.utc
                )
                from datetime import timedelta
                valid_time = valid_dt + timedelta(hours=fhr)

                frames: dict[str, np.ndarray] = {}
                manifests: dict[str, WeatherFrame] = {}

                for var_name, native_arr in variable_arrays.items():
                    var_info = _GFS_VARIABLES[var_name]
                    reprojected = reproject_array(
                        native_arr,
                        src_bounds_wgs84=bbox_wgs84,
                        dst_grid=target_grid,
                        continuous=True,
                        src_nodata=9.999e20,
                        dst_nodata=np.nan,
                    )
                    qc = FrameQC(
                        source=self.source_name,
                        variable=var_name,
                        data_version=f"GFS_{run_date.strftime('%Y%m%d')}T{run_hour:02d}Z",
                        source_resolution=_SOURCE_RESOLUTION,
                        canonical_resolution=canonical_res,
                        processing_version=_PROCESSING_VERSION,
                        units=var_info["canonical_units"],
                        seen_timestamps=self._qc_seen,
                    )
                    manifest, cleaned = qc.run(reprojected, valid_time)
                    frames[var_name] = cleaned
                    manifests[var_name] = manifest

                yield frames, manifests, valid_time
            except Exception as exc:
                log.warning("GFS fhr=%03d failed: %s", fhr, exc)

    def _download_grib2(
        self,
        run_date: datetime,
        run_hour: int,
        fhr: int,
        raw_dir: Path,
    ) -> Path:
        """Download a single GFS GRIB2 file from NOMADS."""
        date_str = run_date.strftime("%Y%m%d")
        fname = f"gfs.t{run_hour:02d}z.pgrb2.0p25.f{fhr:03d}"
        local_path = raw_dir / f"{date_str}_{run_hour:02d}Z_{fname}"

        if local_path.exists():
            log.debug("Cache hit: %s", local_path.name)
            return local_path

        url = f"{_NOMADS_BASE}/gfs.{date_str}/{run_hour:02d}/atmos/{fname}"
        log.info("Downloading GFS: %s", url)
        urllib.request.urlretrieve(url, str(local_path))
        return local_path

    def _parse_grib2(
        self,
        path: Path,
        bbox_wgs84: list[float],
    ) -> dict[str, np.ndarray]:
        """Parse GFS GRIB2 file, crop to bbox, return dict of variable arrays."""
        try:
            import os
            import sys
            
            # Windows DLL discovery fix for eccodes via findlibs
            if os.name == 'nt':
                lib_path = os.path.join(sys.prefix, 'Library', 'bin')
                if os.path.exists(lib_path):
                    os.environ['ECCODES_DIR'] = lib_path
                    os.environ['PATH'] = lib_path + os.pathsep + os.environ.get('PATH', '')
                    if hasattr(os, 'add_dll_directory'):
                        os.add_dll_directory(lib_path)
            
            import cfgrib
            import xarray as xr
        except Exception as e:
            raise RuntimeError(
                f"cfgrib or xarray not available. Install with: conda install -c conda-forge cfgrib xarray. Error: {e}"
            )

        west, south, east, north = bbox_wgs84
        result: dict[str, np.ndarray] = {}

        for var_name, meta in _GFS_VARIABLES.items():
            try:
                filter_keys = {
                    "typeOfLevel": meta["typeOfLevel"],
                }
                ds = xr.open_dataset(
                    str(path),
                    engine="cfgrib",
                    filter_by_keys=filter_keys,
                    indexpath="",
                )
                # Try to find the variable by shortName
                short = meta.get("shortName", "")
                for ds_var in ds.data_vars:
                    arr = ds[ds_var].values
                    if arr.ndim == 2:
                        # Crop to bbox if lat/lon coords are available
                        if "latitude" in ds.coords and "longitude" in ds.coords:
                            lats = ds.latitude.values
                            lons = ds.longitude.values
                            # Handle 0–360 longitude
                            if lons.max() > 180:
                                lons = np.where(lons > 180, lons - 360, lons)
                            lat_mask = (lats >= south) & (lats <= north)
                            lon_mask = (lons >= west) & (lons <= east)
                            arr = arr[np.ix_(lat_mask, lon_mask)]
                        result[var_name] = arr.astype(np.float32)
                        break
                ds.close()
            except Exception as exc:
                log.debug("Could not parse %s from %s: %s", var_name, path.name, exc)

        return result
