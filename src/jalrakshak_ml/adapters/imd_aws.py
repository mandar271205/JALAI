"""IMD Automatic Weather Station (AWS) adapter interface stub.

IMD operates a network of Automatic Weather Stations across India providing
hourly surface observations: rainfall, temperature, humidity, wind speed/direction,
pressure.

Access is controlled by IMD — no public API is available as of the current date.

THIS IS AN INTERFACE STUB — no fake/synthetic data is generated here.
"""
from __future__ import annotations

from jalrakshak_ml.adapters.base import WeatherAdapter


class IMDAWSAdapter(WeatherAdapter):
    """
    Interface stub for IMD Automatic Weather Station surface observations.

    Expected variables (when implemented)
    --------------------------------------
    - rainfall       : 15-min/hourly accumulated rainfall (mm)
    - temperature    : Air temperature at 2m (°C → K canonical)
    - humidity       : Relative humidity (%)
    - wind_speed     : Wind speed at 10m (m/s)
    - wind_direction : Wind direction (degrees from north)
    - pressure       : Station pressure (hPa)

    To implement:
    1. Obtain IMD API key / SFTP credentials.
    2. Implement fetch() — download CSV/XML observation files.
    3. Implement parse() — decode station data, align to UTC timestamps.
    4. Implement to_weather_frame() — spatial interpolate to grid if needed,
       run QC, emit WeatherFrame manifests.

    ⚠ AWS observations are point data — spatial interpolation (IDW/Kriging)
      is required to produce gridded fields. Document this explicitly.
    """

    source_name = "imd_aws"

    def fetch(self, **kwargs):
        raise NotImplementedError(
            "IMD AWS credentials not configured. "
            "Obtain access from India Meteorological Department."
        )

    def parse(self, raw_path, **kwargs):
        raise NotImplementedError("IMD AWS parse() not implemented.")

    def to_weather_frame(self, data, **kwargs):
        raise NotImplementedError("IMD AWS to_weather_frame() not implemented.")
