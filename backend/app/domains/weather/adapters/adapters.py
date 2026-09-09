from typing import Any

from app.domains.weather.adapters.base import WeatherSourceAdapter


class RadarAdapter(WeatherSourceAdapter):
    def __init__(self, source_id: str = "imd-radar-mumbai"):
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> str:
        return "RADAR"

    async def list_available(self) -> list[dict[str, Any]]:
        return []

    async def fetch(self, source_item_id: str) -> bytes:
        return b"RADAR_BINARY_DOPPLER_SIM"

    async def parse_metadata(self, raw_bytes: bytes) -> dict[str, Any]:
        return {"source_id": self._source_id, "source_type": "RADAR", "crs": "EPSG:4326"}

    async def normalize(self, raw_bytes: bytes) -> dict[str, Any]:
        return {"canonical_unit": "mm/h", "max_rate_mm_h": 50.0}

    async def health_check(self) -> dict[str, Any]:
        return {"status": "HEALTHY", "source_id": self._source_id}


class SatelliteAdapter(WeatherSourceAdapter):
    def __init__(self, source_id: str = "insat-3d-precipitation"):
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> str:
        return "SATELLITE"

    async def list_available(self) -> list[dict[str, Any]]:
        return []

    async def fetch(self, source_item_id: str) -> bytes:
        return b"SATELLITE_HDF5_SIM"

    async def parse_metadata(self, raw_bytes: bytes) -> dict[str, Any]:
        return {"source_id": self._source_id, "source_type": "SATELLITE", "crs": "EPSG:4326"}

    async def normalize(self, raw_bytes: bytes) -> dict[str, Any]:
        return {"canonical_unit": "mm/h"}

    async def health_check(self) -> dict[str, Any]:
        return {"status": "HEALTHY", "source_id": self._source_id}


class GaugeTelemetryAdapter(WeatherSourceAdapter):
    def __init__(self, source_id: str = "cwc-telemetry-mithi"):
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> str:
        return "GAUGE"

    async def list_available(self) -> list[dict[str, Any]]:
        return []

    async def fetch(self, source_item_id: str) -> bytes:
        return b"GAUGE_TELEMETRY_CSV"

    async def parse_metadata(self, raw_bytes: bytes) -> dict[str, Any]:
        return {"source_id": self._source_id, "source_type": "GAUGE"}

    async def normalize(self, raw_bytes: bytes) -> dict[str, Any]:
        return {"water_level_m": 3.45}

    async def health_check(self) -> dict[str, Any]:
        return {"status": "HEALTHY", "source_id": self._source_id}


class NWPAdapter(WeatherSourceAdapter):
    def __init__(self, source_id: str = "nwp-wrf-forecast"):
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> str:
        return "NUMERICAL_MODEL"

    async def list_available(self) -> list[dict[str, Any]]:
        return []

    async def fetch(self, source_item_id: str) -> bytes:
        return b"WRF_GRIB2_NETCDF_SIM"

    async def parse_metadata(self, raw_bytes: bytes) -> dict[str, Any]:
        return {"source_id": self._source_id, "source_type": "NUMERICAL_MODEL"}

    async def normalize(self, raw_bytes: bytes) -> dict[str, Any]:
        return {"forecast_horizon_hours": 72}

    async def health_check(self) -> dict[str, Any]:
        return {"status": "HEALTHY", "source_id": self._source_id}
