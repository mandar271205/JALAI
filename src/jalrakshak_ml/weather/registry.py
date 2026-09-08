"""Versioned weather source registry for JalRakshak AI (SIH26071).

Maintains authoritative metadata for all supported, candidate, and interface-only
meteorological sources.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceRegistryEntry:
    """Metadata specification for a meteorological data source."""

    source_id: str
    source_name: str
    source_type: str
    product: str
    provider: str
    spatial_resolution: str
    cadence_minutes: int
    expected_latency_minutes: int
    access_mode: str
    credentials_requirement: str
    temporal_coverage: str
    available_variables: tuple[str, ...]
    unit_semantics: dict[str, str]
    live_status: str
    adapter_class: str
    source_priority: int
    fallback_role: str
    eligibility_mode: str  # "GROUND_TRUTH_ONLY" | "REALTIME_ELIGIBLE" | "EXPERIMENTAL_ONLY"
    access_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


WEATHER_SOURCE_REGISTRY: dict[str, SourceRegistryEntry] = {
    "nasa_gpm_imerg_v07": SourceRegistryEntry(
        source_id="nasa_gpm_imerg_v07",
        source_name="NASA GPM IMERG V07 (Final Run)",
        source_type="satellite_precipitation",
        product="3B-HHR.MS.MRG.3IMERG",
        provider="NASA_GPM",
        spatial_resolution="0.1_deg (~11 km over Mumbai)",
        cadence_minutes=30,
        expected_latency_minutes=150000,  # ~3.5 months for Final run gauge correction
        access_mode="earthdata_https",
        credentials_requirement="EARTHDATA_LOGIN",
        temporal_coverage="2000-06-01 to present (delayed)",
        available_variables=("precipitation_rate", "precipitation_uncalibrated", "quality_index"),
        unit_semantics={
            "precipitation_rate": "mm/h",
            "precipitation_uncalibrated": "mm/h",
            "quality_index": "dimensionless",
        },
        live_status="ARCHIVE_ONLY",
        adapter_class="jalrakshak_ml.weather.adapters.gpm.GPMAdapter",
        source_priority=3,
        fallback_role="ground_truth_and_research_baseline",
        eligibility_mode="GROUND_TRUTH_ONLY",
        access_notes="Final run uses monthly rain gauge calibration. Latency is ~3.5 months. Not real-time eligible.",
    ),
    "noaa_gfs_0p25": SourceRegistryEntry(
        source_id="noaa_gfs_0p25",
        source_name="NOAA GFS (Global Forecast System 0.25 Degree)",
        source_type="nwp_forecast",
        product="atmos/gfs.t{cycle}z.pgrb2.0p25.f{lead}",
        provider="NOAA_NCEP",
        spatial_resolution="0.25_deg (~28 km over Mumbai)",
        cadence_minutes=60,
        expected_latency_minutes=360,  # 6 hours operational buffer
        access_mode="aws_s3_https_range",
        credentials_requirement="NONE",
        temporal_coverage="2021-present (AWS Registry of Open Data)",
        available_variables=(
            "precipitation_rate",
            "accumulated_precipitation",
            "wind_u10",
            "wind_v10",
            "wind_speed_10m",
            "wind_direction_10m",
            "temperature_2m",
            "relative_humidity_2m",
            "surface_pressure",
            "cape",
            "precipitable_water",
        ),
        unit_semantics={
            "precipitation_rate": "mm/h",
            "accumulated_precipitation": "mm",
            "wind_u10": "m/s",
            "wind_v10": "m/s",
            "wind_speed_10m": "m/s",
            "wind_direction_10m": "degrees_from_north",
            "temperature_2m": "K",
            "relative_humidity_2m": "%",
            "surface_pressure": "Pa",
            "cape": "J/kg",
            "precipitable_water": "kg/m^2",
        },
        live_status="READY",
        adapter_class="jalrakshak_ml.weather.adapters.gfs_rich.GFSRichAdapter",
        source_priority=4,
        fallback_role="synoptic_nwp_guidance",
        eligibility_mode="REALTIME_ELIGIBLE",
        access_notes="Open access via NOAA Big Data Program on AWS. Strictly enforced 6h publication lag.",
    ),
    "imd_dwr_mumbai": SourceRegistryEntry(
        source_id="imd_dwr_mumbai",
        source_name="IMD Doppler Weather Radar Mumbai (Colaba / Veravali)",
        source_type="weather_radar",
        product="radar_volume_scan_c_band",
        provider="IMD",
        spatial_resolution="~1_km (polar range gates 150-250m)",
        cadence_minutes=15,
        expected_latency_minutes=20,
        access_mode="imd_internal_network",
        credentials_requirement="IMD_MOU_REQUIRED",
        temporal_coverage="UNVERIFIED",
        available_variables=(
            "reflectivity_dbz",
            "rainfall_rate_mm_h",
            "radial_velocity_ms",
            "quality_mask",
        ),
        unit_semantics={
            "reflectivity_dbz": "dBZ",
            "rainfall_rate_mm_h": "mm/h",
            "radial_velocity_ms": "m/s",
            "quality_mask": "binary_flag",
        },
        live_status="AUTH_REQUIRED",
        adapter_class="jalrakshak_ml.weather.adapters.imd_radar.IMDRadarAdapter",
        source_priority=1,
        fallback_role="primary_nowcast_observation",
        eligibility_mode="REALTIME_ELIGIBLE",
        access_notes="Direct volume scan data requires institutional MoU with IMD. No credentials present in repo.",
    ),
    "mosdac_insat_3d_3dr": SourceRegistryEntry(
        source_id="mosdac_insat_3d_3dr",
        source_name="ISRO MOSDAC INSAT-3D / INSAT-3DR",
        source_type="geostationary_satellite",
        product="insat_l2_imager_products",
        provider="ISRO_MOSDAC",
        spatial_resolution="4_km (IR/WV) / 1_km (VIS)",
        cadence_minutes=30,
        expected_latency_minutes=45,
        access_mode="mosdac_portal_api",
        credentials_requirement="MOSDAC_TOKEN_REQUIRED",
        temporal_coverage="2013-present (INSAT-3D), 2016-present (INSAT-3DR)",
        available_variables=(
            "tir1_brightness_temp",
            "tir2_brightness_temp",
            "water_vapor_brightness_temp",
            "cloud_top_temp",
            "satellite_qpe_hem",
            "satellite_qpe_imsra",
        ),
        unit_semantics={
            "tir1_brightness_temp": "K",
            "tir2_brightness_temp": "K",
            "water_vapor_brightness_temp": "K",
            "cloud_top_temp": "K",
            "satellite_qpe_hem": "mm/h",
            "satellite_qpe_imsra": "mm/h",
        },
        live_status="AUTH_REQUIRED",
        adapter_class="jalrakshak_ml.weather.adapters.mosdac_insat.MOSDACAdapter",
        source_priority=2,
        fallback_role="secondary_satellite_observation",
        eligibility_mode="REALTIME_ELIGIBLE",
        access_notes="Requires institutional user registration and token on https://www.mosdac.gov.in/.",
    ),
}


def get_source_entry(source_id: str) -> SourceRegistryEntry:
    """Retrieve entry from registry or raise KeyError."""
    if source_id not in WEATHER_SOURCE_REGISTRY:
        raise KeyError(
            f"Unknown source_id={source_id!r}. Available sources: {list(WEATHER_SOURCE_REGISTRY.keys())}"
        )
    return WEATHER_SOURCE_REGISTRY[source_id]


def list_registered_sources() -> list[dict[str, Any]]:
    """Return list of all registered source metadata dictionaries."""
    return [entry.to_dict() for entry in WEATHER_SOURCE_REGISTRY.values()]
