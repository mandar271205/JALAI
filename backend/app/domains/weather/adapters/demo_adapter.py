import hashlib
from datetime import UTC, datetime
from typing import Any

from app.domains.weather.adapters.base import WeatherSourceAdapter


class FileSystemDemoAdapter(WeatherSourceAdapter):
    """
    Replays frozen historical/demo weather data completely offline.
    Never relies on live external API keys.
    """

    def __init__(self, source_id: str = "demo-offline-radar", source_type: str = "RADAR"):
        self._source_id = source_id
        self._source_type = source_type
        # Frozen synthetic precipitation raster payload
        self._frozen_data = (
            b"DEMO_PRECIP_GRID_20260908_MONSOON_REFLECTIVITY_TIFF_HEADER" + b"\x00" * 128
        )

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> str:
        return self._source_type

    async def list_available(self) -> list[dict[str, Any]]:
        now = datetime.now(UTC).isoformat()
        return [
            {
                "item_id": f"{self._source_id}_20260908_0930",
                "timestamp": now,
                "file_size": len(self._frozen_data),
                "format": "GeoTIFF",
            }
        ]

    async def fetch(self, source_item_id: str) -> bytes:
        return self._frozen_data

    async def parse_metadata(self, raw_bytes: bytes) -> dict[str, Any]:
        checksum = hashlib.sha256(raw_bytes).hexdigest()
        return {
            "source_id": self._source_id,
            "source_type": self._source_type,
            "sha256": checksum,
            "bounds": [72.75, 18.88, 73.02, 19.28],
            "crs": "EPSG:4326",
            "resolution_m": 250,
            "timestamp": datetime.now(UTC).isoformat(),
            "provenance": "IMD Doppler Radar Colaba Archival Stream",
        }

    async def normalize(self, raw_bytes: bytes) -> dict[str, Any]:
        return {
            "canonical_unit": "mm/h",
            "max_rate_mm_h": 68.5,
            "mean_rate_mm_h": 32.1,
            "spatial_projection": "EPSG:4326",
            "artifact_format": "Cloud-Optimized-GeoTIFF",
            "grid_dimensions": [512, 512],
        }

    async def health_check(self) -> dict[str, Any]:
        return {
            "status": "HEALTHY",
            "adapter": "FileSystemDemoAdapter",
            "mode": "offline_replay",
            "latency_ms": 1.2,
        }
