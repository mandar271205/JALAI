"""MOSDAC adapter interface stub.

MOSDAC (Meteorological and Oceanographic Satellite Data Archival Centre)
provides satellite QPE, cloud-top temperature, and atmospheric moisture products.

Access requires institutional registration at: https://www.mosdac.gov.in/

THIS IS AN INTERFACE STUB — not yet implemented.
The pipeline must continue to run without MOSDAC data.
When access is granted, implement fetch/parse/to_weather_frame here.
No MOSDAC-specific logic should exist anywhere else in the codebase.
"""
from __future__ import annotations

from jalrakshak_ml.adapters.base import WeatherAdapter


class MOSDACAdapter(WeatherAdapter):
    """
    Interface stub for MOSDAC satellite QPE / cloud / moisture data.

    Expected eventual variables
    ---------------------------
    - satellite_qpe   : Satellite Quantitative Precipitation Estimate (mm/h)
    - cloud_top_temp  : Cloud-top brightness temperature (K)
    - precipitable_water : Atmospheric moisture column (mm)

    To implement:
    1. Register at https://www.mosdac.gov.in/ and obtain credentials.
    2. Add credentials to config or environment variables (never hardcode).
    3. Implement fetch() to download HDF5/netCDF products.
    4. Implement parse() to extract variables with correct units.
    5. Implement to_weather_frame() to run QC and emit WeatherFrame manifests.
    """

    source_name = "mosdac"

    def fetch(self, **kwargs):
        raise NotImplementedError(
            "MOSDAC access not yet configured. "
            "Register at https://www.mosdac.gov.in/ and implement this adapter."
        )

    def parse(self, raw_path, **kwargs):
        raise NotImplementedError("MOSDAC parse() not implemented.")

    def to_weather_frame(self, data, **kwargs):
        raise NotImplementedError("MOSDAC to_weather_frame() not implemented.")
