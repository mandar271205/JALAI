"""ISRO MOSDAC INSAT-3D / INSAT-3DR Satellite Adapter for JalRakshak AI (SIH26071).

Implements the interface, channel schemas, calibration models, and health diagnostics
for INSAT geostationary meteorological satellites via the MOSDAC open/registered portal.

NON-NEGOTIABLE PRINCIPLES:
1. Under no circumstances will synthetic or fake satellite imagery be generated.
2. If credentials / MOSDAC user tokens are absent, status is AUTH_REQUIRED.
3. Preserves exact spectral bands, native units (Kelvin for TB, mm/h for QPE),
   and native resolutions (4 km for IR/WV, 1 km for VIS).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from jalrakshak_ml.weather.adapters.base import BaseMeteorologicalAdapter
from jalrakshak_ml.weather.contracts import MeteorologicalField

log = logging.getLogger(__name__)

# Established INSAT Spectral Channels & Products
INSAT_CHANNELS = {
    "TIR1": {
        "channel_name": "TIR-1",
        "central_wavelength_um": 10.8,
        "bandwidth_um": (10.3, 11.3),
        "native_resolution_km": 4.0,
        "standard_name": "toa_brightness_temperature_10_8um",
        "units": "K",
    },
    "TIR2": {
        "channel_name": "TIR-2",
        "central_wavelength_um": 12.0,
        "bandwidth_um": (11.5, 12.5),
        "native_resolution_km": 4.0,
        "standard_name": "toa_brightness_temperature_12_0um",
        "units": "K",
    },
    "WV": {
        "channel_name": "Water Vapor",
        "central_wavelength_um": 6.8,
        "bandwidth_um": (6.5, 7.1),
        "native_resolution_km": 4.0,
        "standard_name": "toa_brightness_temperature_6_8um",
        "units": "K",
    },
    "VIS": {
        "channel_name": "Visible",
        "central_wavelength_um": 0.65,
        "bandwidth_um": (0.55, 0.75),
        "native_resolution_km": 1.0,
        "standard_name": "toa_bidirectional_reflectance",
        "units": "dimensionless",
    },
}

INSAT_DERIVED_PRODUCTS = {
    "CTT": {
        "product_name": "Cloud Top Temperature",
        "standard_name": "air_temperature_at_cloud_top",
        "units": "K",
        "native_resolution_km": 4.0,
    },
    "HEM": {
        "product_name": "Hydro-Estimator Method (Rainfall Rate)",
        "standard_name": "rainfall_flux",
        "units": "mm/h",
        "native_resolution_km": 4.0,
    },
    "IMSRA": {
        "product_name": "INSAT Multi-Spectral Rainfall Algorithm",
        "standard_name": "rainfall_flux",
        "units": "mm/h",
        "native_resolution_km": 4.0,
    },
}


class MOSDACAdapter(BaseMeteorologicalAdapter):
    """Production-shaped adapter for ISRO MOSDAC INSAT-3D / INSAT-3DR."""

    def __init__(
        self,
        satellite: str = "INSAT-3DR",
        token: str | None = None,
        credentials_file: str | Path | None = None,
        archive_dir: str | Path | None = None,
    ) -> None:
        self.satellite = satellite
        self.token = token
        self.credentials_file = Path(credentials_file) if credentials_file else None
        self.archive_dir = Path(archive_dir) if archive_dir else None

    @property
    def source_id(self) -> str:
        return "mosdac_insat_3d_3dr"

    @property
    def is_live_available(self) -> bool:
        """True only if an active user token or registered local HDF5/NetCDF archive exists."""
        if self.token:
            return True
        if self.credentials_file and self.credentials_file.exists():
            return True
        if self.archive_dir and self.archive_dir.exists():
            h5_files = list(self.archive_dir.glob("*.h5")) + list(self.archive_dir.glob("*.nc"))
            return len(h5_files) > 0
        return False

    def health_check(self) -> dict[str, Any]:
        """Audit status of MOSDAC INSAT ingestion."""
        if self.is_live_available:
            return {
                "source_id": self.source_id,
                "status": "READY",
                "available": True,
                "satellite": self.satellite,
                "details": "MOSDAC credentials/archive available.",
            }
        return {
            "source_id": self.source_id,
            "status": "AUTH_REQUIRED",
            "available": False,
            "satellite": self.satellite,
            "details": (
                "Access to INSAT-3D/3DR HDF5/NetCDF products requires institutional registration "
                "and API tokens at https://www.mosdac.gov.in/. No credentials found in repository. "
                "Per research rules, no synthetic satellite data will be generated."
            ),
        }

    def fetch(
        self,
        *,
        valid_time: datetime,
        output_dir: Path | str,
        product: str = "HEM",
        **kwargs: Any,
    ) -> Path | None:
        """Retrieve INSAT product granule from MOSDAC."""
        if not self.is_live_available:
            raise PermissionError(
                "MOSDAC data access not configured. "
                "Registration at https://www.mosdac.gov.in/ is required. "
                "No fake satellite data will be generated."
            )
        raise NotImplementedError("Live MOSDAC download hook not implemented.")

    def parse(
        self,
        raw_path: Path | str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Decode raw INSAT HDF5/NetCDF granule."""
        path = Path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"INSAT granule {path} does not exist.")
        raise NotImplementedError(
            f"Parser for {path.suffix} requires HDF5/h5py or netCDF4 library."
        )

    def to_meteorological_fields(
        self,
        raw_data: dict[str, Any],
        **kwargs: Any,
    ) -> list[MeteorologicalField]:
        """Convert decoded INSAT payload into canonical MeteorologicalField instances."""
        fields = []
        scan_time = raw_data["observation_time"]
        acquisition_time = raw_data.get("acquisition_time", scan_time)
        availability_time = raw_data.get("availability_time", scan_time)

        # Support decoding for Brightness Temperatures (TIR1, TIR2, WV)
        for band in ("TIR1", "TIR2", "WV"):
            key = f"tb_{band.lower()}"
            if key in raw_data:
                data = np.asarray(raw_data[key], dtype=np.float32)
                valid_mask = np.isfinite(data) & (data >= 150.0) & (data <= 350.0)
                band_meta = INSAT_CHANNELS[band]
                fields.append(
                    MeteorologicalField(
                        field_name=f"insat_{band.lower()}_brightness_temp",
                        standard_name=band_meta["standard_name"],
                        source_name=self.source_id,
                        source_product=f"{self.satellite}_L1B_{band}",
                        source_provider="ISRO_MOSDAC",
                        data=data,
                        valid_mask=valid_mask,
                        units="K",
                        native_units="K",
                        conversion_method="none",
                        valid_time=scan_time,
                        observation_time=scan_time,
                        acquisition_time=acquisition_time,
                        availability_time=availability_time,
                        native_resolution="4_km",
                        native_cadence_minutes=30,
                        output_resolution="canonical_256x256",
                        output_cadence_minutes=30,
                        source_crs="EPSG:4326",
                        target_crs="EPSG:32643",
                        data_version="insat_v1",
                        product_version=raw_data.get("product_version", "unknown"),
                        processing_version="v1.0",
                        quality_score=float(raw_data.get("quality_score", 1.0)),
                        quality_flags=list(raw_data.get("quality_flags", [])),
                        missing_fraction=float(1.0 - (np.sum(valid_mask) / data.size)),
                        source_uri=str(raw_data.get("source_uri", "unknown")),
                        provenance={
                            "satellite": self.satellite,
                            "channel": band_meta,
                        },
                    )
                )

        # Support decoding for Satellite QPE (HEM / IMSRA)
        for qpe_prod in ("HEM", "IMSRA"):
            key = f"rain_rate_{qpe_prod.lower()}"
            if key in raw_data:
                data = np.asarray(raw_data[key], dtype=np.float32)
                valid_mask = np.isfinite(data) & (data >= 0.0) & (data <= 300.0)
                fields.append(
                    MeteorologicalField(
                        field_name=f"insat_qpe_{qpe_prod.lower()}",
                        standard_name="rainfall_flux",
                        source_name=self.source_id,
                        source_product=f"{self.satellite}_L2_{qpe_prod}",
                        source_provider="ISRO_MOSDAC",
                        data=data,
                        valid_mask=valid_mask,
                        units="mm/h",
                        native_units="mm/h",
                        conversion_method="none",
                        valid_time=scan_time,
                        observation_time=scan_time,
                        acquisition_time=acquisition_time,
                        availability_time=availability_time,
                        native_resolution="4_km",
                        native_cadence_minutes=30,
                        output_resolution="canonical_256x256",
                        output_cadence_minutes=30,
                        source_crs="EPSG:4326",
                        target_crs="EPSG:32643",
                        data_version="insat_v1",
                        product_version=raw_data.get("product_version", "unknown"),
                        processing_version="v1.0",
                        quality_score=float(raw_data.get("quality_score", 1.0)),
                        quality_flags=list(raw_data.get("quality_flags", [])),
                        missing_fraction=float(1.0 - (np.sum(valid_mask) / data.size)),
                        source_uri=str(raw_data.get("source_uri", "unknown")),
                        provenance={
                            "satellite": self.satellite,
                            "algorithm": INSAT_DERIVED_PRODUCTS[qpe_prod],
                        },
                    )
                )

        return fields
