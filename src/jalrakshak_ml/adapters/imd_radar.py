"""IMD Doppler Weather Radar adapter interface stub.

IMD operates dual-polarisation Doppler radars across India including at
Mumbai (Colaba). Radar products are not publicly distributed — access
requires a formal MoU with IMD.

THIS IS AN INTERFACE STUB — no fake/synthetic data is generated here.
When IMD radar access is obtained, implement this adapter.
The pipeline must continue to run without IMD Radar data.
"""
from __future__ import annotations

from jalrakshak_ml.adapters.base import WeatherAdapter


class IMDRadarAdapter(WeatherAdapter):
    """
    Interface stub for IMD Doppler Weather Radar data.

    Expected variables (when implemented)
    --------------------------------------
    - reflectivity_dbz   : Radar reflectivity (dBZ)
    - rainfall_rate      : QPE from reflectivity-Z relationship (mm/h)
    - radial_velocity    : Doppler radial wind velocity (m/s)

    To implement:
    1. Obtain IMD MoU / data access credentials.
    2. Implement fetch() — retrieve raw radar volume scans (HDF5/IRIS format).
    3. Implement parse() — decode radar data with appropriate library (wradlib).
    4. Implement to_weather_frame() — run QC and emit WeatherFrame manifests.

    ⚠ Do NOT label GPM IMERG or GFS data as "IMD Radar" under any circumstances.
    """

    source_name = "imd_radar"

    def fetch(self, **kwargs):
        raise NotImplementedError(
            "IMD Radar credentials/access not configured. "
            "This adapter requires a formal IMD data sharing agreement."
        )

    def parse(self, raw_path, **kwargs):
        raise NotImplementedError("IMD Radar parse() not implemented.")

    def to_weather_frame(self, data, **kwargs):
        raise NotImplementedError("IMD Radar to_weather_frame() not implemented.")
