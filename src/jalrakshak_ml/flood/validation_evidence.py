"""Historical flood evidence ingestion, verification, and categorical distinction framework.

Enforces strict separation between:
1. observed_extent (satellite SAR/optical flood delineations)
2. reported_location (geotagged field or citizen incident points)
3. modelled_extent (numerical simulation flood extents)
4. susceptibility (dimensionless terrain flood tendency ranking)
5. hydraulic_depth (continuous physical water depth in metres)

These concepts must NEVER be silently interchanged.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class FloodEvidenceType(str, enum.Enum):
    OBSERVED_EXTENT = "observed_extent"
    REPORTED_LOCATION = "reported_location"
    MODELLED_EXTENT = "modelled_extent"
    SUSCEPTIBILITY = "susceptibility"
    HYDRAULIC_DEPTH = "hydraulic_depth"


@dataclass(frozen=True)
class FloodEvidenceItem:
    evidence_id: str
    evidence_type: FloodEvidenceType | str
    source: str
    event_id: str
    timestamp_utc: str
    crs: str
    data_path: str | None
    is_empirical: bool
    units: str
    resolution: str
    provenance: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        etype = (
            self.evidence_type.value
            if isinstance(self.evidence_type, enum.Enum)
            else str(self.evidence_type)
        )
        if etype not in [e.value for e in FloodEvidenceType]:
            raise ValueError(f"Unknown flood evidence type '{etype}'")

        if etype == FloodEvidenceType.SUSCEPTIBILITY.value and self.units != "dimensionless":
            raise ValueError("Susceptibility evidence must have dimensionless units, never meters")

        if etype == FloodEvidenceType.HYDRAULIC_DEPTH.value and self.units not in ("m", "meters"):
            raise ValueError("Hydraulic depth evidence must have units in meters")

        if etype == FloodEvidenceType.OBSERVED_EXTENT.value and not self.is_empirical:
            raise ValueError("Observed extent must be marked as empirical")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FloodValidationManifest:
    evidence_items: list[FloodEvidenceItem]
    real_flood_validation_data_available: bool
    authoritative_extent_raster_present: bool
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_items": [item.to_dict() for item in self.evidence_items],
            "real_flood_validation_data_available": self.real_flood_validation_data_available,
            "authoritative_extent_raster_present": self.authoritative_extent_raster_present,
            "summary": self.summary,
        }


class FloodEvidenceIngestor:
    """Manages and audits historical flood validation data sources."""

    def __init__(self, search_dir: Path | str = "data/processed/flood") -> None:
        self.search_dir = Path(search_dir)

    def audit_evidence_availability(self) -> FloodValidationManifest:
        items: list[FloodEvidenceItem] = []

        # Check for susceptibility raster (this is susceptibility, NOT depth or observed extent)
        susc_path = self.search_dir / "susceptibility_v1.tif"
        if susc_path.is_file():
            items.append(
                FloodEvidenceItem(
                    evidence_id="mumbai_relative_susceptibility_v1",
                    evidence_type=FloodEvidenceType.SUSCEPTIBILITY,
                    source="Copernicus DEM GLO-30 + OSM Waterways Multi-Criteria Index",
                    event_id="static_monsoon_baseline",
                    timestamp_utc="2026-09-09T00:00:00Z",
                    crs="EPSG:32643",
                    data_path=str(susc_path),
                    is_empirical=False,  # multi-criteria model, not field observation
                    units="dimensionless",
                    resolution="256x256 (~160m)",
                    provenance={"method": "weighted_linear_combination", "quantity": "relative_flood_susceptibility"},
                )
            )

        # Check for remote-sensing SAR inundation masks or official flood extent files
        sar_files = list(self.search_dir.glob("*sar_extent*.tif")) + list(self.search_dir.glob("*observed_flood*.tif"))
        for sf in sar_files:
            items.append(
                FloodEvidenceItem(
                    evidence_id=sf.stem,
                    evidence_type=FloodEvidenceType.OBSERVED_EXTENT,
                    source="Copernicus Sentinel-1 SAR Water Mask",
                    event_id="historical_monsoon",
                    timestamp_utc="UNKNOWN",
                    crs="EPSG:32643",
                    data_path=str(sf),
                    is_empirical=True,
                    units="binary_extent",
                    resolution="10m",
                    provenance={"sensor": "Sentinel-1 C-SAR"},
                )
            )

        # Validate all items
        for it in items:
            it.validate()

        has_observed_extent = any(
            (it.evidence_type == FloodEvidenceType.OBSERVED_EXTENT.value or
             it.evidence_type == FloodEvidenceType.OBSERVED_EXTENT) and it.is_empirical
            for it in items
        )

        # Real validation data is only available if empirical observed extent or depth exists
        real_data_available = has_observed_extent

        counts = {
            e.value: sum(
                1 for it in items
                if (it.evidence_type.value if isinstance(it.evidence_type, enum.Enum) else str(it.evidence_type)) == e.value
            )
            for e in FloodEvidenceType
        }

        summary = {
            "total_items": len(items),
            "counts_by_type": counts,
            "real_flood_validation_data_available": real_data_available,
            "authoritative_extent_raster_present": has_observed_extent,
            "status_message": (
                "Empirical satellite flood extent (Sentinel-1 SAR) or BMC waterlogging spot surveys "
                "are NOT yet acquired locally. REAL_FLOOD_VALIDATION_DATA_AVAILABLE remains False."
                if not real_data_available
                else "Empirical flood validation extent available."
            ),
        }

        return FloodValidationManifest(
            evidence_items=items,
            real_flood_validation_data_available=real_data_available,
            authoritative_extent_raster_present=has_observed_extent,
            summary=summary,
        )
