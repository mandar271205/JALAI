"""GPM IMERG historical precipitation adapter.

Source: NASA GPM IMERG Final Run Half-Hourly v07
        (GPM_3IMERGHH, resolution 0.1°×0.1°, 30-min intervals)

Access: NASA GES DISC HTTPS with Earthdata credentials in ~/.netrc
        Add the following to ~/.netrc:
          machine urs.earthdata.nasa.gov login <USERNAME> password <PASSWORD>

⚠ IMPORTANT LABELLING NOTE:
   GPM IMERG is a post-processed satellite product with ~3-month latency for
   the Final Run. It must NOT be labelled as real-time radar data or used
   for issuing real-time alerts. Use it as a training/validation baseline only.

Architecture: All source-specific logic is contained here. The pipeline
receives canonical numpy arrays + WeatherFrame manifests. No IMERG-specific
assumptions leak downstream.
"""
from __future__ import annotations

import logging
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import numpy as np

from jalrakshak_ml.preprocessing.grid import reproject_array
from jalrakshak_ml.qc.frame_qc import FrameQC
from jalrakshak_ml.schemas.weather_frame import WeatherFrame

log = logging.getLogger(__name__)

# Product constants
_PRODUCT = "GPM_3IMERGHH"
_VERSION = "07"
_VARIABLE = "precipitationCal"           # Gauge-corrected (preferred)
_UNITS_NATIVE = "mm/hr"
_UNITS_CANONICAL = "mm/h"               # Same magnitude, canonical name
_SOURCE_RESOLUTION = "0.1 deg (~11 km)"
_PROCESSING_VERSION = "0.2.0"

# GES DISC HTTPS base URL template
# Full URL: https://gpm1.gesdisc.eosdis.nasa.gov/data/GPM_L3/GPM_3IMERGHH.07/
#           YYYY/DDD/3B-HHR.MS.MRG.3IMERG.YYYYMMDD-S{HH}MM{SS}-E{HH}MM{SS}.MMMM.V07B.HDF5
_GESDISC_BASE = (
    "https://gpm1.gesdisc.eosdis.nasa.gov/data/GPM_L3/"
    f"{_PRODUCT}.{_VERSION}/{{year}}/{{doy:03d}}/"
)

# Coordinate bounds of the global IMERG grid
_IMERG_LAT_MIN, _IMERG_LAT_MAX = -89.95, 89.95   # 0.1° step
_IMERG_LON_MIN, _IMERG_LON_MAX = -179.95, 179.95


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iter_half_hour_times(start_date: datetime, end_date: datetime) -> Iterator[datetime]:
    """Yield native IMERG timestamps in ``[start_date, end_date)``."""
    original_start = _as_utc(start_date)
    start = original_start.replace(
        minute=0 if original_start.minute < 30 else 30,
        second=0,
        microsecond=0,
    )
    end = _as_utc(end_date)
    if start < original_start:
        start += timedelta(minutes=30)
    current = start
    while current < end:
        yield current
        current += timedelta(minutes=30)


def granule_filename(valid_time: datetime, product_version: str = _VERSION) -> str:
    """Return the official filename for one half-hourly IMERG granule."""
    valid_time = _as_utc(valid_time)
    if valid_time.minute not in (0, 30) or valid_time.second or valid_time.microsecond:
        raise ValueError("IMERG valid_time must be aligned to a 30-minute boundary")
    start_hhmm = f"{valid_time.hour:02d}{valid_time.minute:02d}00"
    end_m = 29 if valid_time.minute == 0 else 59
    end_hhmm = f"{valid_time.hour:02d}{end_m:02d}59"
    elapsed_str = f"{valid_time.hour * 60 + valid_time.minute:04d}"
    date_str = valid_time.strftime("%Y%m%d")
    return (
        f"3B-HHR.MS.MRG.3IMERG.{date_str}-S{start_hhmm}-E{end_hhmm}"
        f".{elapsed_str}.V{product_version}B.HDF5"
    )


def _netrc_configured() -> bool:
    """Check if ~/.netrc has Earthdata credentials."""
    netrc = Path.home() / ".netrc"
    if not netrc.exists():
        return False
    return "urs.earthdata.nasa.gov" in netrc.read_text()


class GPMIMERGAdapter:
    """
    Fetch, QC, and reproject NASA GPM IMERG Half-Hourly data for a pilot bbox.

    Usage
    -----
    adapter = GPMIMERGAdapter()
    for frame, manifest in adapter.fetch(
            bbox_wgs84=[72.75, 18.85, 73.05, 19.30],
            start_date=datetime(2023, 7, 1, tzinfo=timezone.utc),
            end_date=datetime(2023, 7, 3, tzinfo=timezone.utc),
            raw_dir=Path("data/raw/gpm"),
            target_grid=grid,
    ):
        # frame: np.ndarray shape (256, 256), units mm/h
        # manifest: WeatherFrame
    """

    source_name = "gpm_imerg"

    def __init__(self, product_version: str = _VERSION):
        self.product_version = product_version
        self._qc_seen: set[str] = set()

    def fetch(
        self,
        bbox_wgs84: list[float],
        start_date: datetime,
        end_date: datetime,
        raw_dir: Path,
        target_grid: dict,
        max_workers: int = 1,
    ) -> Iterator[tuple[np.ndarray, WeatherFrame]]:
        """
        Download IMERG granules for [start_date, end_date) and yield
        (canonical_array, WeatherFrame) pairs for each half-hourly frame.

        Parameters
        ----------
        bbox_wgs84 : [west, south, east, north]
        start_date / end_date : UTC datetimes (end exclusive)
        raw_dir : where to preserve raw HDF5 files
        target_grid : dict from build_target_grid()
        """
        if not _netrc_configured():
            raise AuthenticationRequired(
                "NASA Earthdata credentials not found in ~/.netrc\n"
                "1. Register free at: https://urs.earthdata.nasa.gov/\n"
                "2. Add to ~/.netrc:\n"
                "   machine urs.earthdata.nasa.gov login <USERNAME> password <PASSWORD>\n"
                "3. chmod 600 ~/.netrc"
            )

        raw_dir.mkdir(parents=True, exist_ok=True)

        qc = FrameQC(
            source=self.source_name,
            variable="rainfall_rate",
            data_version=f"IMERG_V{self.product_version}",
            source_resolution=_SOURCE_RESOLUTION,
            canonical_resolution=f"~{target_grid['resolution_m']:.0f}m @ {target_grid['width']}x{target_grid['height']}",
            processing_version=_PROCESSING_VERSION,
            units=_UNITS_CANONICAL,
            expected_units=_UNITS_CANONICAL,
            seen_timestamps=self._qc_seen,
        )

        if _as_utc(end_date) <= _as_utc(start_date):
            raise ValueError("end_date must be later than start_date")
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        valid_times = list(iter_half_hour_times(start_date, end_date))
            
        import concurrent.futures
        
        log.info(f"Downloading {len(valid_times)} GPM files concurrently...")
        # Pre-download all files concurrently
        def download_worker(vt):
            try:
                return vt, self._download_granule(vt, raw_dir)
            except Exception as exc:
                return vt, exc
                
        downloaded_paths = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(download_worker, vt): vt for vt in valid_times}
            for future in concurrent.futures.as_completed(futures):
                vt, res = future.result()
                downloaded_paths[vt] = res

        # Process sequentially in correct temporal order
        for valid_time in valid_times:
            res = downloaded_paths[valid_time]
            if isinstance(res, Exception):
                log.warning("Skipping %s due to download error: %s", valid_time.isoformat(), res)
                continue
                
            raw_path = res
            try:
                native_array, lat_arr, lon_arr = self._parse_hdf5(raw_path)
                cropped = self._crop_to_bbox(native_array, lat_arr, lon_arr, bbox_wgs84)
                reprojected = reproject_array(
                    cropped,
                    src_bounds_wgs84=bbox_wgs84,
                    dst_grid=target_grid,
                    continuous=True,
                    src_nodata=-9999.0,
                    dst_nodata=np.nan,
                )
                manifest, cleaned = qc.run(reprojected, valid_time)
                yield cleaned, manifest
            except AuthenticationRequired:
                raise
            except Exception as exc:
                log.warning("Skipping %s during parse: %s", valid_time.isoformat(), exc)

    def _download_granule(self, valid_time: datetime, raw_dir: Path) -> Path:
        """Download a single IMERG granule HDF5 file if not already cached."""
        import requests
        
        valid_time = _as_utc(valid_time)
        doy = valid_time.timetuple().tm_yday
        year = valid_time.year
        fname = granule_filename(valid_time, self.product_version)
        local_path = raw_dir / fname

        if local_path.exists():
            log.debug("Cache hit: %s", fname)
            return local_path

        base_url = _GESDISC_BASE.format(year=year, doy=doy)
        url = base_url + fname
        
        log.info("Downloading %s using requests", url)
        
        session = requests.Session()
        
        import netrc
        try:
            secrets = netrc.netrc()
            auth_info = secrets.authenticators("urs.earthdata.nasa.gov")
            if auth_info:
                session.auth = (auth_info[0], auth_info[2])
        except Exception as e:
            log.warning("Could not parse .netrc: %s", e)
        
        try:
            response = session.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            if "text/html" in response.headers.get("Content-Type", ""):
                raise RuntimeError(f"Earthdata authentication failed (downloaded HTML). Please ensure you have approved the 'NASA GESDISC DATA ARCHIVE' application in your Earthdata account.")
                
            temp_path = local_path.with_suffix('.tmp')
            try:
                with open(temp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                temp_path.replace(local_path)
            finally:
                temp_path.unlink(missing_ok=True)
            
        except requests.exceptions.RequestException as e:
            log.error(f"Download failed: {e}")
            raise RuntimeError(f"Download failed: {e}")

        return local_path

    def _parse_hdf5(self, path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Parse IMERG HDF5 and return (precipitation array, lat, lon)."""
        import h5py

        with h5py.File(str(path), "r") as f:
            # IMERG HDF5 structure: /Grid/precipitation shape = (1, nlat, nlon) or (ntime, nlat, nlon)
            precip = f["Grid"]["precipitation"][:]          # shape (time, lat, lon) or (1, lat, lon)
            lat = f["Grid"]["lat"][:]                  # 1-D
            lon = f["Grid"]["lon"][:]                  # 1-D

        # Squeeze time dimension if present
        if precip.ndim == 3:
            precip = precip[0]    # (lon, lat)
            
        # Transpose to (lat, lon)
        precip = precip.T

        # IMERG stores fill value as -9999.9
        precip = np.where(precip < -9000, np.nan, precip.astype(np.float32))

        return precip, lat, lon

    def _crop_to_bbox(
        self,
        array: np.ndarray,
        lat: np.ndarray,
        lon: np.ndarray,
        bbox_wgs84: list[float],
    ) -> np.ndarray:
        """Crop IMERG grid to pilot bounding box."""
        west, south, east, north = bbox_wgs84
        lat_mask = (lat >= south) & (lat <= north)
        lon_mask = (lon >= west) & (lon <= east)
        cropped = array[np.ix_(lat_mask, lon_mask)]
        return cropped


class AuthenticationRequired(RuntimeError):
    """Raised when NASA Earthdata credentials are missing."""
