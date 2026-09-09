"""Data source capability registry: implementation is not population."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SourceCapability:
    source_id: str
    configured: bool
    credentials_required: bool
    credentials_available: bool
    historical_available: bool
    near_realtime_capable: bool
    actually_integrated: bool
    actually_populated: bool
    spatial_resolution: str
    temporal_resolution: str
    known_latency: str
    latency_is_observed_or_assumed: str
    scientific_role: str

    def validate(self) -> None:
        if self.latency_is_observed_or_assumed not in {"OBSERVED", "ASSUMED", "UNKNOWN"}:
            raise ValueError("Latency basis must be OBSERVED, ASSUMED, or UNKNOWN")
        if self.actually_populated and not self.actually_integrated:
            raise ValueError("A source cannot be populated without integration")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


def default_source_capabilities() -> list[SourceCapability]:
    """Repository-evidenced Phase 8 source status; no network probes are implied."""
    return [
        SourceCapability(
            "GPM_FINAL",
            True,
            True,
            False,
            True,
            False,
            True,
            True,
            "0.1 degree native",
            "30 min",
            "months",
            "ASSUMED",
            "historical rainfall reference; satellite, not radar",
        ),
        SourceCapability(
            "GPM_IMERG_NRT",
            False,
            True,
            False,
            False,
            True,
            False,
            False,
            "0.1 degree native",
            "30 min",
            "hours",
            "ASSUMED",
            "near-real-time satellite precipitation",
        ),
        SourceCapability(
            "NOAA_GFS",
            True,
            False,
            True,
            True,
            True,
            True,
            True,
            "0.25 degree native",
            "hourly forecast steps",
            "operational-cycle dependent",
            "ASSUMED",
            "coarse NWP rainfall guidance",
        ),
        SourceCapability(
            "IMD_DWR",
            False,
            True,
            False,
            False,
            True,
            False,
            False,
            "site/product dependent",
            "unknown",
            "unknown",
            "UNKNOWN",
            "weather radar; not integrated",
        ),
        SourceCapability(
            "MOSDAC_INSAT",
            False,
            True,
            False,
            False,
            True,
            False,
            False,
            "product dependent",
            "product dependent",
            "unknown",
            "UNKNOWN",
            "satellite observation; not integrated",
        ),
        SourceCapability(
            "COPERNICUS_DEM",
            True,
            False,
            True,
            True,
            False,
            True,
            True,
            "30 m nominal",
            "static",
            "not applicable",
            "OBSERVED",
            "terrain elevation input",
        ),
        SourceCapability(
            "OPENSTREETMAP",
            True,
            False,
            True,
            True,
            True,
            True,
            True,
            "vector feature dependent",
            "snapshot",
            "community update dependent",
            "UNKNOWN",
            "roads, waterways, facilities; not complete drainage",
        ),
        SourceCapability(
            "POPULATION",
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            "unavailable",
            "unavailable",
            "unavailable",
            "UNKNOWN",
            "exposure input; missing",
        ),
        SourceCapability(
            "FLOOD_VALIDATION",
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            "unavailable",
            "event dependent",
            "unavailable",
            "UNKNOWN",
            "observed flood extent/depth reference; missing",
        ),
    ]
