"""NASA GPM IMERG V07 Meteorological Adapter for JalRakshak AI (SIH26071).

Adapts GPM IMERG Final Run half-hourly products to canonical MeteorologicalField
instances. Enforces the strict rule that GPM Final Run is GROUND_TRUTH_ONLY with
a multi-month latency, and not eligible for real-time operational nowcast inputs.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from jalrakshak_ml.weather.adapters.base import BaseMeteorologicalAdapter
from jalrakshak_ml.weather.contracts import MeteorologicalField

# Nominal latency of GPM Final Run is ~3.5 months (approx 105 days)
GPM_FINAL_RUN_LATENCY_DAYS = 105


class GPMAdapter(BaseMeteorologicalAdapter):
    """Adapter for NASA GPM IMERG V07 half-hourly precipitation."""

    def __init__(
        self,
        processed_dir: str | Path | None = None,
        raw_dir: str | Path | None = None,
    ) -> None:
        self.processed_dir = Path(processed_dir) if processed_dir else None
        self.raw_dir = Path(raw_dir) if raw_dir else None

    @property
    def source_id(self) -> str:
        return "nasa_gpm_imerg_v07"

    @property
    def is_live_available(self) -> bool:
        """Final run is archive-only and not available for live real-time feeds."""
        return False

    def health_check(self) -> dict[str, Any]:
        """Audit status of GPM local archive."""
        has_archive = self.processed_dir and self.processed_dir.exists()
        return {
            "source_id": self.source_id,
            "status": "READY" if has_archive else "ARCHIVE_ONLY",
            "available": bool(has_archive),
            "eligibility_mode": "GROUND_TRUTH_ONLY",
            "details": (
                "NASA GPM IMERG V07 Final Run is gauge-calibrated with ~3.5 months latency. "
                "Classified as GROUND_TRUTH_ONLY for historical training and benchmark evaluation. "
                "Not eligible for real-time operational nowcast input."
            ),
        }

    def fetch(
        self,
        *,
        valid_time: datetime,
        output_dir: Path | str,
        **kwargs: Any,
    ) -> Path | None:
        """Fetch raw granule from Earthdata (requires credentials)."""
        raise PermissionError(
            "GPM IMERG Final Run download requires active Earthdata credentials in ~/.netrc. "
            "For offline execution, use existing processed/raw frames in data/."
        )

    def parse(
        self,
        raw_path: Path | str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Parse raw HDF5 or local numpy array."""
        path = Path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"GPM file {path} not found")
        if path.suffix == ".npy":
            arr = np.load(path)
            return {"precipitation": arr, "units": "mm/h"}
        raise NotImplementedError("Raw HDF5 parsing requires h5py")

    def to_meteorological_fields(
        self,
        raw_data: dict[str, Any],
        valid_time: datetime,
        **kwargs: Any,
    ) -> list[MeteorologicalField]:
        """Convert GPM array into canonical MeteorologicalField."""
        data = np.asarray(raw_data["precipitation"], dtype=np.float32)
        valid_mask = np.isfinite(data) & (data >= 0.0)
        # Final run latency is ~105 days
        availability_time = valid_time + timedelta(days=GPM_FINAL_RUN_LATENCY_DAYS)
        acquisition_time = kwargs.get("acquisition_time", availability_time)

        field = MeteorologicalField(
            field_name="rainfall_rate",
            standard_name="rainfall_flux",
            source_name=self.source_id,
            source_product="3B-HHR.MS.MRG.3IMERG",
            source_provider="NASA_GPM",
            data=data,
            valid_mask=valid_mask,
            units="mm/h",
            native_units="mm/hr",
            conversion_method="identity",
            valid_time=valid_time,
            observation_time=valid_time,
            acquisition_time=acquisition_time,
            availability_time=availability_time,
            native_resolution="0.1_deg (~11 km)",
            native_cadence_minutes=30,
            output_resolution="canonical_256x256",
            output_cadence_minutes=30,
            source_crs="EPSG:4326",
            target_crs="EPSG:32643",
            data_version="gpm_imerg_v07_mumbai_monsoon_expanded_v1",
            product_version="V07B",
            processing_version="v2.0",
            quality_score=float(kwargs.get("quality_score", 1.0)),
            quality_flags=list(kwargs.get("quality_flags", [])),
            missing_fraction=float(1.0 - (np.sum(valid_mask) / data.size)),
            source_uri=str(raw_data.get("source_uri", "local_archive")),
            provenance={
                "gauge_calibrated": True,
                "latency_mode": "final_run_ground_truth_only",
            },
        )
        return [field]
