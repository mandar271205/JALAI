from abc import ABC, abstractmethod
from typing import Any


class WeatherSourceAdapter(ABC):
    """
    Standard ingestion adapter interface for weather & precipitation telemetry.
    Ensures that raw source artifacts remain immutable with verifiable SHA-256 provenance.
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        pass

    @property
    @abstractmethod
    def source_type(self) -> str:
        # RADAR, SATELLITE, GAUGE, NUMERICAL_MODEL
        pass

    @abstractmethod
    async def list_available(self) -> list[dict[str, Any]]:
        """List newly discovered telemetry files or timestamps."""
        pass

    @abstractmethod
    async def fetch(self, source_item_id: str) -> bytes:
        """Fetch raw binary artifact."""
        pass

    @abstractmethod
    async def parse_metadata(self, raw_bytes: bytes) -> dict[str, Any]:
        """Extract spatial bounds, timestamp, and instrument metadata."""
        pass

    @abstractmethod
    async def normalize(self, raw_bytes: bytes) -> dict[str, Any]:
        """Convert into canonical units (mm/h, EPSG:4326 grid, etc.)."""
        pass

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Verify upstream feed availability."""
        pass
