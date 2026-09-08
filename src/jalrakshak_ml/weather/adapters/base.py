"""Abstract base contract for meteorological data adapters."""
from __future__ import annotations

import abc
from datetime import datetime
from pathlib import Path
from typing import Any

from jalrakshak_ml.weather.contracts import MeteorologicalField


class BaseMeteorologicalAdapter(abc.ABC):
    """Abstract interface for all meteorological adapters.

    Guarantees:
    - Never fabricates synthetic meteorological observations.
    - Accurately reports operational health, access authorization, and latency.
    - Emits strongly-typed, schema-compliant MeteorologicalField objects.
    """

    @property
    @abc.abstractmethod
    def source_id(self) -> str:
        """Unique identifier in WEATHER_SOURCE_REGISTRY."""

    @property
    @abc.abstractmethod
    def is_live_available(self) -> bool:
        """True only if active credentials, network endpoints, or live data feeds exist."""

    @abc.abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Perform diagnostic verification of access, credentials, and data pipeline."""

    @abc.abstractmethod
    def fetch(
        self,
        *,
        valid_time: datetime,
        output_dir: Path | str,
        **kwargs: Any,
    ) -> Path | None:
        """Retrieve raw product granule or message from remote/local store."""

    @abc.abstractmethod
    def parse(
        self,
        raw_path: Path | str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Decode raw file (HDF5, NetCDF, GRIB, IRIS) into raw numpy arrays and metadata."""

    @abc.abstractmethod
    def to_meteorological_fields(
        self,
        raw_data: dict[str, Any],
        **kwargs: Any,
    ) -> list[MeteorologicalField]:
        """Convert decoded product into canonical MeteorologicalField instances."""
