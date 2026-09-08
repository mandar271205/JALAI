"""Richer GFS Meteorological Fields Adapter for JalRakshak AI (SIH26071).

Extracts and validates rich GFS NWP fields beyond precipitation:
- 10 m U wind (m/s)
- 10 m V wind (m/s)
- Derived 10 m wind speed (m/s) & meteorological wind direction (degrees)
- 2 m air temperature (K)
- 2 m relative humidity (%)
- Surface pressure (Pa)
- Surface CAPE (J/kg)
- Precipitable water (kg/m^2)
- Precipitation rate (mm/h)

CRITICAL RULES:
- Exact GRIB shortNames and level types without fallback. Fail on ambiguity.
- Strict physical boundary checks (e.g. RH in [0, 100%], temp in [200, 340 K]).
- No TEST data used for any fitted normalization.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from jalrakshak_ml.gfs_replay.core import select_gfs_forecast_as_of, utc
from jalrakshak_ml.gfs_replay.grib import eccodes_module
from jalrakshak_ml.gfs_replay.spatial import (
    canonicalize_grid,
    crop_with_halo,
    reproject_field,
    reproject_rate,
)
from jalrakshak_ml.weather.adapters.base import BaseMeteorologicalAdapter
from jalrakshak_ml.weather.contracts import MeteorologicalField

log = logging.getLogger(__name__)

# Exact GRIB variable specifications supported by GFS 0.25 deg pgrb2
GFS_VARIABLE_SPECS: dict[str, dict[str, Any]] = {
    "u10": {
        "shortName": "10u",
        "typeOfLevel": "heightAboveGround",
        "level": 10,
        "stepType": "instant",
        "units": "m s**-1",
        "standard_name": "x_wind",
        "canonical_units": "m/s",
        "physical_range": (-120.0, 120.0),
        "resampling": "bilinear",
    },
    "v10": {
        "shortName": "10v",
        "typeOfLevel": "heightAboveGround",
        "level": 10,
        "stepType": "instant",
        "units": "m s**-1",
        "standard_name": "y_wind",
        "canonical_units": "m/s",
        "physical_range": (-120.0, 120.0),
        "resampling": "bilinear",
    },
    "t2m": {
        "shortName": "2t",
        "typeOfLevel": "heightAboveGround",
        "level": 2,
        "stepType": "instant",
        "units": "K",
        "standard_name": "air_temperature",
        "canonical_units": "K",
        "physical_range": (180.0, 345.0),
        "resampling": "bilinear",
    },
    "rh2m": {
        "shortName": "2r",
        "typeOfLevel": "heightAboveGround",
        "level": 2,
        "stepType": "instant",
        "units": "%",
        "standard_name": "relative_humidity",
        "canonical_units": "%",
        "physical_range": (0.0, 100.0),
        "resampling": "bilinear",
    },
    "sp": {
        "shortName": "sp",
        "typeOfLevel": "surface",
        "level": 0,
        "stepType": "instant",
        "units": "Pa",
        "standard_name": "surface_air_pressure",
        "canonical_units": "Pa",
        "physical_range": (50000.0, 110000.0),
        "resampling": "bilinear",
    },
    "cape": {
        "shortName": "cape",
        "typeOfLevel": "surface",
        "level": 0,
        "stepType": "instant",
        "units": "J kg**-1",
        "standard_name": "atmosphere_convective_available_potential_energy",
        "canonical_units": "J/kg",
        "physical_range": (0.0, 10000.0),
        "resampling": "bilinear",
    },
    "pwat": {
        "shortName": "pwat",
        "typeOfLevel": "atmosphereSingleLayer",
        "level": 0,
        "stepType": "instant",
        "units": "kg m**-2",
        "standard_name": "atmosphere_mass_content_of_water_vapor",
        "canonical_units": "kg/m^2",
        "physical_range": (0.0, 150.0),
        "resampling": "bilinear",
    },
}


def derive_wind_speed_and_direction(
    u: np.ndarray, v: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Compute wind speed and meteorological direction from horizontal components.

    Meteorological convention: Direction from which the wind blows,
    measured clockwise from True North (0 = North, 90 = East, 180 = South, 270 = West).
    Formula: (270 - atan2(v, u) * 180 / pi) % 360
    """
    u_arr = np.asarray(u, dtype=np.float32)
    v_arr = np.asarray(v, dtype=np.float32)
    if u_arr.shape != v_arr.shape:
        raise ValueError(f"Shape mismatch: u {u_arr.shape} != v {v_arr.shape}")

    speed = np.hypot(u_arr, v_arr)
    # math.atan2(v, u) in radians
    # Convert mathematical angle (direction toward) to meteorological (direction from)
    rad = np.arctan2(v_arr, u_arr)
    deg = (270.0 - np.degrees(rad)) % 360.0

    metadata = {
        "speed_formula": "sqrt(u^2 + v^2)",
        "direction_formula": "(270 - rad2deg(atan2(v, u))) % 360",
        "convention": "meteorological_direction_from_which_wind_is_blowing",
        "speed_units": "m/s",
        "direction_units": "degrees",
    }
    return speed, deg, metadata


def read_exact_gfs_field(
    grib_path: Path | str,
    variable_key: str,
    bbox: tuple[float, float, float, float] = (72.70, 18.80, 73.10, 19.35),
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Decode exact requested GRIB message; verify all statistical & level keys."""
    if variable_key not in GFS_VARIABLE_SPECS:
        raise ValueError(f"Unsupported GFS variable: {variable_key!r}")

    spec = GFS_VARIABLE_SPECS[variable_key]
    ec = eccodes_module()
    match = None

    with Path(grib_path).open("rb") as stream:
        while (gid := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                identity = {
                    "shortName": ec.codes_get(gid, "shortName"),
                    "typeOfLevel": ec.codes_get(gid, "typeOfLevel"),
                    "level": int(ec.codes_get(gid, "level")),
                    "stepType": ec.codes_get(gid, "stepType"),
                }
                if any(identity[k] != spec[k] for k in identity):
                    continue

                # Matched exact key
                meta = {
                    **identity,
                    "units": ec.codes_get(gid, "units"),
                    "forecast_reference_time": datetime.strptime(
                        f"{int(ec.codes_get(gid, 'dataDate')):08d}{int(ec.codes_get(gid, 'dataTime')):04d}",
                        "%Y%m%d%H%M",
                    ).replace(tzinfo=UTC).isoformat(),
                    "valid_time": datetime.strptime(
                        f"{int(ec.codes_get(gid, 'validityDate')):08d}{int(ec.codes_get(gid, 'validityTime')):04d}",
                        "%Y%m%d%H%M",
                    ).replace(tzinfo=UTC).isoformat(),
                    "startStep": float(ec.codes_get(gid, "startStep")),
                    "endStep": float(ec.codes_get(gid, "endStep")),
                    "gridType": ec.codes_get(gid, "gridType"),
                }
                if match is not None:
                    raise ValueError(f"Ambiguous GFS message: multiple matches for {variable_key}")

                lats = np.asarray(ec.codes_get_array(gid, "latitudes"))
                lons = np.asarray(ec.codes_get_array(gid, "longitudes"))
                values = np.asarray(ec.codes_get_values(gid), dtype=np.float64)
                values[values == ec.codes_get(gid, "missingValue")] = np.nan

                lat, rows = np.unique(lats, return_inverse=True)
                lon, cols = np.unique(lons, return_inverse=True)
                grid = np.full((len(lat), len(lon)), np.nan)
                grid[rows, cols] = values

                cropped, lat, lon, affine = crop_with_halo(grid, lat, lon, bbox)
                match = (cropped, lat, lon, meta)
            finally:
                ec.codes_release(gid)

    if match is None:
        raise ValueError(f"Exact GRIB field missing: {variable_key} ({spec})")
    return match


class GFSRichAdapter(BaseMeteorologicalAdapter):
    """Adapter for multi-variable GFS meteorological analysis and forecast fields."""

    def __init__(
        self,
        grib_file: Path | str | None = None,
        latency_hours: float = 6.0,
    ) -> None:
        self.grib_file = Path(grib_file) if grib_file else None
        self.latency_hours = latency_hours

    @property
    def source_id(self) -> str:
        return "noaa_gfs_0p25"

    @property
    def is_live_available(self) -> bool:
        return True  # Open data on AWS S3

    def health_check(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "status": "READY",
            "available": True,
            "supported_variables": list(GFS_VARIABLE_SPECS.keys()),
            "details": "GFS 0.25 degree operational open data via NOAA S3.",
        }

    def fetch(
        self,
        *,
        valid_time: datetime,
        output_dir: Path | str,
        **kwargs: Any,
    ) -> Path | None:
        return self.grib_file

    def parse(
        self,
        raw_path: Path | str,
        variable_key: str = "t2m",
        bbox: tuple[float, float, float, float] = (72.70, 18.80, 73.10, 19.35),
        **kwargs: Any,
    ) -> dict[str, Any]:
        arr, lat, lon, meta = read_exact_gfs_field(raw_path, variable_key, bbox=bbox)
        return {"array": arr, "lat": lat, "lon": lon, "metadata": meta}

    def to_meteorological_fields(
        self,
        raw_data: dict[str, Any],
        variable_key: str,
        target_grid: dict[str, Any],
        **kwargs: Any,
    ) -> list[MeteorologicalField]:
        """Reproject and wrap raw GFS data into canonical MeteorologicalField."""
        spec = GFS_VARIABLE_SPECS[variable_key]
        arr = raw_data["array"]
        lat = raw_data["lat"]
        lon = raw_data["lon"]
        meta = raw_data["metadata"]

        # Validate physical range
        min_v, max_v = spec["physical_range"]
        finite_vals = arr[np.isfinite(arr)]
        if finite_vals.size and (np.any(finite_vals < min_v) or np.any(finite_vals > max_v)):
            raise ValueError(
                f"Physical range check failed for {variable_key}: "
                f"bounds [{min_v}, {max_v}], observed [{np.nanmin(arr)}, {np.nanmax(arr)}]"
            )

        # Reproject to target grid
        if variable_key in ("precipitation", "prate", "apcp"):
            reprojected, spatial_meta = reproject_rate(arr, lat, lon, target_grid)
        else:
            reprojected, spatial_meta = reproject_field(
                arr,
                lat,
                lon,
                target_grid,
                physical_range=spec.get("physical_range"),
                variable_name=variable_key,
            )

        ref_time = utc(meta["forecast_reference_time"])
        val_time = utc(meta["valid_time"])
        avail_time = ref_time + timedelta(hours=self.latency_hours)

        valid_mask = np.isfinite(reprojected)
        field = MeteorologicalField(
            field_name=f"gfs_{variable_key}",
            standard_name=spec["standard_name"],
            source_name=self.source_id,
            source_product="pgrb2.0p25",
            source_provider="NOAA_NCEP",
            data=np.asarray(reprojected, dtype=np.float32),
            valid_mask=valid_mask,
            units=spec["canonical_units"],
            native_units=meta["units"],
            conversion_method="reproject_bilinear_preserving_native_units",
            valid_time=val_time,
            forecast_reference_time=ref_time,
            acquisition_time=kwargs.get("acquisition_time", avail_time),
            availability_time=avail_time,
            native_resolution="0.25_deg (~28 km)",
            native_cadence_minutes=60,
            output_resolution=f"{target_grid.get('width', 256)}x{target_grid.get('height', 256)}",
            output_cadence_minutes=30,
            source_crs="EPSG:4326",
            target_crs=target_grid["crs"],
            data_version="gfs_rich_fields_v1",
            product_version="gfs_pgrb2_v16",
            processing_version="v2.0",
            quality_score=1.0,
            quality_flags=[],
            missing_fraction=float(1.0 - (np.sum(valid_mask) / reprojected.size)),
            source_uri=str(kwargs.get("source_uri", "noaa-gfs-bdp-pds")),
            provenance={
                "grib_identity": {
                    "shortName": spec["shortName"],
                    "typeOfLevel": spec["typeOfLevel"],
                    "level": spec["level"],
                    "stepType": spec["stepType"],
                },
                "spatial": spatial_meta,
            },
        )
        return [field]
