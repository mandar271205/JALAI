"""Physics Scenario Catalog and Simulation Design Planning.

Prepares reproducible hydrodynamic simulation scenario matrices using genuine
geospatial layers and historical rainfall events, without generating fake flood depths.
Includes defensible simulation dataset size planning for future FNO training.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


@dataclass
class ScenarioDefinition:
    """Definition of a single prospective hydrodynamic simulation scenario."""
    scenario_id: str
    event_id: str
    research_split: str  # train, validation, or test_reserved
    intensity_class: str
    perturbation_family: str
    rainfall_multiplier: float
    roughness_multiplier: float
    initial_soil_saturation: str  # dry, normal, saturated
    elevation_hash: str
    roughness_hash: str
    forcing_format: str
    solver_target: str
    solver_params: dict[str, Any]
    simulated_water_depth_target_available: bool = False
    notes: str = ""


@dataclass
class PhysicsSimulationDesignPlan:
    """Defensible scientific planning for future numerical hydraulic simulations."""
    minimum_viable_simulation_count: int
    preferred_research_grade_simulation_count: int
    split_strategy: str
    event_level_separation: dict[str, list[str]]
    perturbation_families: list[str]
    expected_disk_per_simulation_mb: float
    expected_total_disk_gb_min: float
    expected_total_disk_gb_pref: float
    expected_solver_runtime_sec: str
    fno_data_readiness_threshold: str
    scientific_justification: str


@dataclass
class ScenarioCatalogReport:
    """Authoritative Phase 7 Physics Scenario Catalog and Planning Report."""
    catalog_version: str
    created_at: str
    domain: str
    crs_projected: str
    grid_shape: list[int]
    total_scenarios: int
    scenarios_by_split: dict[str, int]
    scenarios_by_perturbation: dict[str, int]
    simulation_design_plan: dict[str, Any]
    scenarios: list[dict[str, Any]] = field(default_factory=list)


def compute_file_sha256(path: Path) -> str:
    if not path.exists():
        return "UNKNOWN_MISSING"
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class PhysicsScenarioBuilder:
    """Constructs the physics scenario matrix from verified rainfall events and static inputs."""

    # Plausible physical perturbation families
    PERTURBATIONS: ClassVar[list[dict[str, Any]]] = [
        {"name": "baseline", "rain_mult": 1.0, "rough_mult": 1.0, "soil": "normal"},
        {"name": "heavy_rain_surge", "rain_mult": 1.25, "rough_mult": 1.0, "soil": "normal"},
        {"name": "moderate_rain_attenuation", "rain_mult": 0.80, "rough_mult": 1.0, "soil": "normal"},
        {"name": "high_roughness_vegetated", "rain_mult": 1.0, "rough_mult": 1.20, "soil": "normal"},
        {"name": "low_roughness_cleared", "rain_mult": 1.0, "rough_mult": 0.85, "soil": "normal"},
        {"name": "pre_saturated_antecedent", "rain_mult": 1.0, "rough_mult": 1.0, "soil": "saturated"},
    ]

    def __init__(
        self,
        events_catalog_path: Path,
        elevation_path: Path,
        roughness_path: Path,
    ):
        self.events_catalog_path = Path(events_catalog_path)
        self.elevation_path = Path(elevation_path)
        self.roughness_path = Path(roughness_path)

    def load_events(self) -> dict[str, Any]:
        if not self.events_catalog_path.exists():
            raise FileNotFoundError(f"Rainfall catalog not found: {self.events_catalog_path}")
        with open(self.events_catalog_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def build_catalog(self) -> ScenarioCatalogReport:
        events_data = self.load_events()
        elevation_hash = compute_file_sha256(self.elevation_path)
        roughness_hash = compute_file_sha256(self.roughness_path)

        research_splits = events_data.get("research_splits_locked", {})
        train_events = research_splits.get("train", [])
        val_events = research_splits.get("validation", [])
        test_events = research_splits.get("test", [])

        scenarios: list[ScenarioDefinition] = []

        # 1. Generate scenarios for Train events (all 6 perturbation families)
        for eid in train_events:
            for p in self.PERTURBATIONS:
                scen_id = f"scen_train_{eid}_{p['name']}"
                scenarios.append(
                    ScenarioDefinition(
                        scenario_id=scen_id,
                        event_id=eid,
                        research_split="train",
                        intensity_class="HISTORICAL_MONSOON",
                        perturbation_family=p["name"],
                        rainfall_multiplier=p["rain_mult"],
                        roughness_multiplier=p["rough_mult"],
                        initial_soil_saturation=p["soil"],
                        elevation_hash=elevation_hash,
                        roughness_hash=roughness_hash,
                        forcing_format="LISFLOOD_BDY_AND_SWMM_DAT",
                        solver_target="LISFLOOD-FP",
                        solver_params={
                            "sim_time_hours": 12.0,
                            "time_step_sec": 5.0,
                            "cfl_condition": 0.7,
                            "output_interval_sec": 1800.0,
                            "subgrid_channels": False,
                        },
                        simulated_water_depth_target_available=False,
                        notes="Prospective training scenario with controlled physical perturbation.",
                    )
                )

        # 2. Generate scenarios for Validation events (baseline + extreme perturbation only)
        val_perturbations = [
            {"name": "baseline", "rain_mult": 1.0, "rough_mult": 1.0, "soil": "normal"},
            {"name": "pre_saturated_antecedent", "rain_mult": 1.0, "rough_mult": 1.0, "soil": "saturated"},
        ]
        for eid in val_events:
            for p in val_perturbations:
                scen_id = f"scen_val_{eid}_{p['name']}"
                scenarios.append(
                    ScenarioDefinition(
                        scenario_id=scen_id,
                        event_id=eid,
                        research_split="validation",
                        intensity_class="HISTORICAL_MONSOON",
                        perturbation_family=p["name"],
                        rainfall_multiplier=p["rain_mult"],
                        roughness_multiplier=p["rough_mult"],
                        initial_soil_saturation=p["soil"],
                        elevation_hash=elevation_hash,
                        roughness_hash=roughness_hash,
                        forcing_format="LISFLOOD_BDY_AND_SWMM_DAT",
                        solver_target="LISFLOOD-FP",
                        solver_params={
                            "sim_time_hours": 12.0,
                            "time_step_sec": 5.0,
                            "cfl_condition": 0.7,
                            "output_interval_sec": 1800.0,
                            "subgrid_channels": False,
                        },
                        simulated_water_depth_target_available=False,
                        notes="Validation scenario with strict holdout from training.",
                    )
                )

        # 3. Test events are strictly reserved for pure baseline evaluation (no perturbation exploitation)
        for eid in test_events:
            scen_id = f"scen_test_reserved_{eid}_baseline"
            scenarios.append(
                ScenarioDefinition(
                    scenario_id=scen_id,
                    event_id=eid,
                    research_split="test_locked_reserved",
                    intensity_class="HISTORICAL_MONSOON",
                    perturbation_family="baseline",
                    rainfall_multiplier=1.0,
                    roughness_multiplier=1.0,
                    initial_soil_saturation="normal",
                    elevation_hash=elevation_hash,
                    roughness_hash=roughness_hash,
                    forcing_format="LISFLOOD_BDY_AND_SWMM_DAT",
                    solver_target="LISFLOOD-FP",
                    solver_params={
                        "sim_time_hours": 12.0,
                        "time_step_sec": 5.0,
                        "cfl_condition": 0.7,
                        "output_interval_sec": 1800.0,
                        "subgrid_channels": False,
                    },
                    simulated_water_depth_target_available=False,
                    notes="Strictly locked test event; only 1 unperturbed baseline planned for final evaluation.",
                )
            )

        # Count statistics
        split_counts: dict[str, int] = {}
        pert_counts: dict[str, int] = {}
        for s in scenarios:
            split_counts[s.research_split] = split_counts.get(s.research_split, 0) + 1
            pert_counts[s.perturbation_family] = pert_counts.get(s.perturbation_family, 0) + 1

        # Simulation Design Plan
        design_plan = PhysicsSimulationDesignPlan(
            minimum_viable_simulation_count=36,
            preferred_research_grade_simulation_count=len(scenarios),  # 12*6 + 3*2 + 3*1 = 81
            split_strategy="Event-level strict separation: no temporal overlap between train, val, and test splits.",
            event_level_separation={
                "train_events": train_events,
                "validation_events": val_events,
                "test_locked_events": test_events,
            },
            perturbation_families=[p["name"] for p in self.PERTURBATIONS],
            expected_disk_per_simulation_mb=32.0,
            expected_total_disk_gb_min=36 * 32.0 / 1024.0,  # ~1.1 GB
            expected_total_disk_gb_pref=len(scenarios) * 32.0 / 1024.0,  # ~2.5 GB
            expected_solver_runtime_sec="UNKNOWN (Must be measured on actual compute environment; no runtime fabrication)",
            fno_data_readiness_threshold=(
                "At least 70-100 full 2D shallow-water hydrodynamic simulations (LISFLOOD-FP or SWMM 2D) "
                "across diverse monsoon events are required before Fourier Neural Operator (FNO) spatial-temporal "
                "surrogate training is scientifically defensible. Training FNO on fewer runs or on static susceptibility "
                "surrogates is physically invalid and prohibited."
            ),
            scientific_justification=(
                "Fourier Neural Operators learn mapping between infinite-dimensional function spaces (rainfall hyetograph "
                "+ terrain/roughness to dynamic water depth). They require true hydrodynamic differential equation outputs "
                "satisfying Saint-Venant shallow water equations with conservation of mass and momentum."
            ),
        )

        return ScenarioCatalogReport(
            catalog_version="phase7_physics_scenario_catalog_v1",
            created_at="2026-09-09T00:00:00Z",
            domain="Mumbai Metropolitan Region",
            crs_projected="EPSG:32643",
            grid_shape=[256, 256],
            total_scenarios=len(scenarios),
            scenarios_by_split=split_counts,
            scenarios_by_perturbation=pert_counts,
            simulation_design_plan=asdict(design_plan),
            scenarios=[asdict(s) for s in scenarios],
        )
