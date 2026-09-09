"""Physically meaningful hydraulic scenario generation for future solver runs.

Generates scenario definitions and forcing metadata; NEVER fabricates hydraulic results.
"""

from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .physics import PhysicsScenario


class ScenarioFamily(str, enum.Enum):
    HISTORICAL_OBSERVED = "historical_observed"
    OPERATIONAL_FORECAST = "operational_forecast"
    INTENSITY_PERTURBATION = "intensity_perturbation"
    TEMPORAL_REDISTRIBUTION = "temporal_redistribution"
    SPATIAL_PERTURBATION = "spatial_perturbation"


@dataclass(frozen=True)
class PerturbationMetadata:
    is_observation: bool
    scenario_family: str
    base_event: str
    scaling_factor: float
    temporal_shift_minutes: int
    spatial_shift_cells: tuple[int, int]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScenarioGenerator:
    """Generates structured scenario parameterizations with reproducible hashes."""

    def __init__(
        self,
        dem_path: str,
        roughness_path: str,
        drainage_network_path: str | None,
        crs: str = "EPSG:32643",
        grid_shape: tuple[int, int] = (256, 256),
    ) -> None:
        self.dem_path = dem_path
        self.roughness_path = roughness_path
        self.drainage_network_path = drainage_network_path
        self.crs = crs
        self.grid_shape = grid_shape

    def generate_historical_scenario(
        self,
        event_id: str,
        rainfall_path: str,
        start_time: str,
        end_time: str,
        temporal_resolution_minutes: int = 30,
        boundary_conditions: dict[str, Any] | None = None,
        infiltration_parameters: dict[str, Any] | None = None,
    ) -> PhysicsScenario:
        provenance = {
            "is_observation": True,
            "scenario_family": ScenarioFamily.HISTORICAL_OBSERVED.value,
            "rainfall_event": event_id,
            "rainfall_source": "gpm_imerg_v07",
            "synthetic": False,
        }
        b_cond = boundary_conditions or {"downstream_water_level_m": 0.0, "tide_cycle": "semi-diurnal"}
        infilt = infiltration_parameters or {"method": "Horton", "f0_mm_h": 75.0, "fc_mm_h": 12.5, "decay_k": 4.14}
        scenario_id = f"hist_{event_id}_{temporal_resolution_minutes}m"
        return PhysicsScenario(
            scenario_id=scenario_id,
            rainfall_forcing_path=rainfall_path,
            rainfall_units="mm/h",
            start_time=start_time,
            end_time=end_time,
            temporal_resolution_minutes=temporal_resolution_minutes,
            dem_path=self.dem_path,
            roughness_path=self.roughness_path,
            drainage_network_path=self.drainage_network_path,
            boundary_conditions=b_cond,
            infiltration_parameters=infilt,
            crs=self.crs,
            grid_shape=self.grid_shape,
            provenance=provenance,
        )

    def generate_perturbed_scenarios(
        self,
        base_scenario: PhysicsScenario,
        intensity_factors: tuple[float, ...] = (0.8, 1.2, 1.5),
        temporal_shifts: tuple[int, ...] = (-30, 30),
    ) -> list[PhysicsScenario]:
        """Generate stratified perturbations, explicitly tagging them as scenarios, NOT observations."""
        scenarios: list[PhysicsScenario] = []
        base_event = base_scenario.provenance.get("rainfall_event", "unknown")

        # Intensity perturbations
        for factor in intensity_factors:
            if np.isclose(factor, 1.0):
                continue
            meta = PerturbationMetadata(
                is_observation=False,
                scenario_family=ScenarioFamily.INTENSITY_PERTURBATION.value,
                base_event=base_event,
                scaling_factor=float(factor),
                temporal_shift_minutes=0,
                spatial_shift_cells=(0, 0),
                description=f"Rainfall intensity scaled by {factor:.2f}x",
            )
            scen_id = f"pert_intensity_{base_event}_x{int(factor * 100):03d}"
            provenance = {
                **base_scenario.provenance,
                **meta.to_dict(),
                "synthetic": False,
                "is_scenario_not_observation": True,
            }
            scen = PhysicsScenario(
                scenario_id=scen_id,
                rainfall_forcing_path=base_scenario.rainfall_forcing_path,
                rainfall_units=base_scenario.rainfall_units,
                start_time=base_scenario.start_time,
                end_time=base_scenario.end_time,
                temporal_resolution_minutes=base_scenario.temporal_resolution_minutes,
                dem_path=base_scenario.dem_path,
                roughness_path=base_scenario.roughness_path,
                drainage_network_path=base_scenario.drainage_network_path,
                boundary_conditions=base_scenario.boundary_conditions,
                infiltration_parameters=base_scenario.infiltration_parameters,
                crs=base_scenario.crs,
                grid_shape=base_scenario.grid_shape,
                provenance=provenance,
                assumed_parameters=(f"intensity_factor:{factor:.2f}",),
            )
            scenarios.append(scen)

        # Temporal redistribution perturbations
        for shift in temporal_shifts:
            if shift == 0:
                continue
            meta = PerturbationMetadata(
                is_observation=False,
                scenario_family=ScenarioFamily.TEMPORAL_REDISTRIBUTION.value,
                base_event=base_event,
                scaling_factor=1.0,
                temporal_shift_minutes=int(shift),
                spatial_shift_cells=(0, 0),
                description=f"Rainfall peak timing shifted by {shift:+d}m",
            )
            prefix = "early" if shift < 0 else "late"
            scen_id = f"pert_temporal_{base_event}_{prefix}_{abs(shift)}m"
            provenance = {
                **base_scenario.provenance,
                **meta.to_dict(),
                "synthetic": False,
                "is_scenario_not_observation": True,
            }
            scen = PhysicsScenario(
                scenario_id=scen_id,
                rainfall_forcing_path=base_scenario.rainfall_forcing_path,
                rainfall_units=base_scenario.rainfall_units,
                start_time=base_scenario.start_time,
                end_time=base_scenario.end_time,
                temporal_resolution_minutes=base_scenario.temporal_resolution_minutes,
                dem_path=base_scenario.dem_path,
                roughness_path=base_scenario.roughness_path,
                drainage_network_path=base_scenario.drainage_network_path,
                boundary_conditions=base_scenario.boundary_conditions,
                infiltration_parameters=base_scenario.infiltration_parameters,
                crs=base_scenario.crs,
                grid_shape=base_scenario.grid_shape,
                provenance=provenance,
                assumed_parameters=(f"temporal_shift_minutes:{shift}",),
            )
            scenarios.append(scen)

        return scenarios


def write_scenario_manifest(scenarios: list[PhysicsScenario], output_path: str | Path) -> dict[str, Any]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for sc in scenarios:
        records.append({
            "scenario_id": sc.scenario_id,
            "hash": sc.stable_hash(),
            "is_observation": sc.provenance.get("is_observation", False),
            "scenario_family": sc.provenance.get("scenario_family", "unknown"),
            "rainfall_forcing_path": sc.rainfall_forcing_path,
            "rainfall_units": sc.rainfall_units,
            "crs": sc.crs,
            "grid_shape": list(sc.grid_shape),
            "boundary_conditions": sc.boundary_conditions,
            "infiltration_parameters": sc.infiltration_parameters,
            "assumed_parameters": list(sc.assumed_parameters),
        })
    manifest = {
        "manifest_version": "physics_scenarios_v1",
        "scenario_count": len(scenarios),
        "scenarios": records,
    }
    raw = json.dumps(manifest, sort_keys=True, allow_nan=False).encode()
    manifest["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
