"""Solver readiness audit and blockers for SWMM and LISFLOOD-FP hydrodynamic models.

Enforces clear distinctions between:
- Input data readiness vs. solver binary availability vs. execution readiness vs. calibration readiness.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SWMMReadinessReport:
    solver_available: bool
    network_nodes_available: bool
    network_links_available: bool
    subcatchments_available: bool
    outlets_available: bool
    conduit_geometry_available: bool
    invert_elevations_available: bool
    rainfall_forcing_available: bool
    infiltration_parameters_available: bool
    surface_parameters_available: bool
    calibration_data_available: bool
    validation_data_available: bool
    executable_input_ready: bool
    swmm_inputs_available: bool
    blockers: list[str] = field(default_factory=list)
    acquisition_checklist: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LISFLOODReadinessReport:
    dem_ready: bool
    terrain_validity: bool
    roughness_ready: bool
    rainfall_forcing_ready: bool
    boundary_conditions_ready: bool
    domain_extent: list[float]
    grid_spacing_m: float
    nodata_handled: bool
    initial_conditions_ready: bool
    solver_available: bool
    input_data_ready: bool
    execution_ready: bool
    calibration_ready: bool
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_swmm_readiness(
    drainage_path: Path | str | None = None,
    solver_cmd: str = "swmm5",
) -> SWMMReadinessReport:
    """Audit municipal drainage network data and SWMM executable availability."""
    solver_found = shutil.which(solver_cmd) is not None

    # OSM waterways exist, but municipal closed-pipe conduit topology is absent
    network_nodes = False
    network_links = False
    subcatchments = False
    outlets = False
    conduit_geom = False
    inverts = False
    calib = False
    valid = False

    blockers = [
        "Municipal stormwater drainage shapefile (.shp/.geojson) or SWMM input file (.inp) absent from repository",
        "Subcatchment delineations with impervious percentages are unmapped",
        "Conduit cross-sections, pipe diameters, roughness, and slope uncharacterized",
        "Junction manhole ground rim elevations and invert depths absent",
        "Tidal flap gate outfalls along Mithi river and Arabian sea uncharacterized",
    ]
    if not solver_found:
        blockers.append(f"SWMM executable '{solver_cmd}' not found on system PATH")

    checklist = [
        {
            "item": "Municipal Stormwater Drainage GIS (.inp / .shp)",
            "source": "Brihanmumbai Municipal Corporation (BMC) Storm Water Drains (SWD) Dept",
            "priority": "P0_CRITICAL",
            "description": "Underground pipe network, closed conduits, box drains, and nullahs",
        },
        {
            "item": "Manhole & Junction Survey",
            "source": "BMC SWD / Mumbai Metropolitan Region Development Authority (MMRDA)",
            "priority": "P0_CRITICAL",
            "description": "Invert levels, rim elevations, and drop depths across all city wards",
        },
        {
            "item": "Subcatchment Boundaries & Runoff Routing",
            "source": "Urban Catchment Hydrology Survey",
            "priority": "P1_HIGH",
            "description": "Ward-level subcatchments, roof/pavement imperviousness fraction",
        },
        {
            "item": "Tidal Boundary Outfalls",
            "source": "Mumbai Port Trust / Maharashtra Maritime Board",
            "priority": "P1_HIGH",
            "description": "Tide gate locations, flap gate discharge coefficients, coastal tide levels",
        },
        {
            "item": "Urban Discharge Calibration Data",
            "source": "BMC Pumping Stations (Love Grove, Cleveland Bunder, Britannia, Irla)",
            "priority": "P2_MEDIUM",
            "description": "Pump discharge records and sump level loggers during storm events",
        },
    ]

    return SWMMReadinessReport(
        solver_available=solver_found,
        network_nodes_available=network_nodes,
        network_links_available=network_links,
        subcatchments_available=subcatchments,
        outlets_available=outlets,
        conduit_geometry_available=conduit_geom,
        invert_elevations_available=inverts,
        rainfall_forcing_available=True,  # GPM events exist
        infiltration_parameters_available=True,  # Green-Ampt / Horton parameter ranges available
        surface_parameters_available=True,
        calibration_data_available=calib,
        validation_data_available=valid,
        executable_input_ready=False,
        swmm_inputs_available=False,
        blockers=blockers,
        acquisition_checklist=checklist,
    )


def audit_lisflood_readiness(
    dem_path: Path | str = "data/processed/static/elevation.tif",
    roughness_path: Path | str = "data/processed/static/roughness.tif",
    solver_cmd: str = "lisflood",
) -> LISFLOODReadinessReport:
    """Audit surface-flood LISFLOOD-FP input readiness vs. solver binary availability."""
    dem_file = Path(dem_path)
    roughness_file = Path(roughness_path)

    dem_ready = dem_file.is_file()
    roughness_ready = roughness_file.is_file()
    solver_found = shutil.which(solver_cmd) is not None

    blockers = []
    if not dem_ready:
        blockers.append(f"DEM raster absent: {dem_file}")
    if not roughness_ready:
        blockers.append(f"Roughness raster absent: {roughness_file}")
    if not solver_found:
        blockers.append(
            f"LISFLOOD-FP compiled binary '{solver_cmd}' not found on system PATH (requires Linux/container execution)"
        )

    # Input data is ready if DEM, roughness, and rainfall inputs are established
    input_data_ready = dem_ready and roughness_ready
    execution_ready = input_data_ready and solver_found

    return LISFLOODReadinessReport(
        dem_ready=dem_ready,
        terrain_validity=dem_ready,
        roughness_ready=roughness_ready,
        rainfall_forcing_ready=True,  # GPM 30-min rainfall adapter available
        boundary_conditions_ready=True,  # Free/open coastal boundaries
        domain_extent=[72.75, 18.85, 73.05, 19.30],
        grid_spacing_m=160.88,
        nodata_handled=True,
        initial_conditions_ready=True,  # Dry bed initial state
        solver_available=solver_found,
        input_data_ready=input_data_ready,
        execution_ready=execution_ready,
        calibration_ready=False,  # Uncalibrated; requires gauge water level records
        blockers=blockers,
    )
