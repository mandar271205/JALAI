"""Authoritative scientific claim gates and integrity verification.

A feature can exist in code while scientific status remains false.
Readiness flags must NEVER be converted into scientific evidence claims.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScientificClaimGates:
    # Phase 5 Implementation & Readiness
    PHASE_5_IMPLEMENTATION_HARDENED: bool = True
    FLOOD_SUSCEPTIBILITY_EXECUTABLE: bool = True
    SUSCEPTIBILITY_IS_NOT_DEPTH: bool = True
    PHYSICS_ORCHESTRATION_READY: bool = True
    SWMM_INPUTS_AVAILABLE: bool = False
    LISFLOOD_FP_INPUTS_AVAILABLE: bool = False
    REAL_PHYSICS_SIMULATION_EXECUTED: bool = False
    PHYSICS_DATASET_BUILDER_HARDENED: bool = True
    GENUINE_FNO_TARGETS_AVAILABLE: bool = False
    FNO_ARCHITECTURE_READY: bool = True
    FNO_TRAINING_STARTED: bool = False
    FNO_VALIDATED: bool = False

    # Exposure & Vulnerability
    EXPOSURE_ENGINE_EXECUTABLE: bool = True
    REAL_EXPOSURE_DATA_AVAILABLE: bool = False
    VULNERABILITY_ENGINE_EXECUTABLE: bool = True
    REAL_VULNERABILITY_DATA_AVAILABLE: bool = False

    # Risk & Uncertainty
    HEV_RISK_ENGINE_EXECUTABLE: bool = True
    PROBABILISTIC_RISK_READY: bool = True
    UNCERTAINTY_PROPAGATION_READY: bool = True
    EXPLAINABILITY_ENGINE_READY: bool = True

    # Citizen Verification
    CITIZEN_VERIFICATION_FOUNDATION_READY: bool = True
    CITIZEN_REAL_ML_AVAILABLE: bool = False

    # Benchmark & Isolation
    FINAL_BENCHMARK_HARNESS_READY: bool = True
    LOCKED_TEST_TOUCHED: bool = False
    PHASE_4E_TRAINING_STARTED: bool = False
    FABRICATED_DEPTH_USED: bool = False
    FAKE_PHYSICS_TRUTH_USED: bool = False
    GIT_PUSHED: bool = False
    REMOTE_MODIFIED: bool = False

    # Phase 7 Genuine Data Readiness & Physics Gates
    PHASE_7_DATA_READINESS_HARDENED: bool = True
    GENUINE_BUILDING_DATA_AVAILABLE: bool = False
    GENUINE_ROAD_DATA_AVAILABLE: bool = True
    GENUINE_CRITICAL_FACILITY_DATA_AVAILABLE: bool = True
    GENUINE_POPULATION_DATA_AVAILABLE: bool = False
    LAND_COVER_REAL_DATA_AVAILABLE: bool = False
    ROUGHNESS_LAYER_READY: bool = True
    ROUGHNESS_CALIBRATED: bool = False
    GENUINE_DRAINAGE_EVIDENCE_AVAILABLE: bool = True
    MUNICIPAL_DRAINAGE_NETWORK_AVAILABLE: bool = False
    SWMM_EXECUTION_READY: bool = False
    LISFLOOD_INPUT_DATA_READY: bool = True
    LISFLOOD_SOLVER_AVAILABLE: bool = False
    LISFLOOD_EXECUTION_READY: bool = False
    REAL_FLOOD_VALIDATION_DATA_AVAILABLE: bool = False
    VULNERABILITY_PROXY_DATA_AVAILABLE: bool = True
    PHYSICS_SCENARIO_CATALOG_READY: bool = True

    # Phase 9 Flood-Physics Execution Readiness (Workstream H)
    PHYSICS_DOMAIN_READY: bool = True          # DEM + roughness + grid verified
    RAINFALL_FORCING_READY: bool = True         # .bdy forcing file exists
    LISFLOOD_EXECUTABLE: bool = False           # solver binary on PATH
    LISFLOOD_SMOKE_EXECUTED: bool = False       # at least one tiny genuine run
    GENUINE_SOLVER_OUTPUT_AVAILABLE: bool = False  # validated depth NetCDF/raster exists
    PHYSICS_DATASET_READY: bool = False         # frozen manifest with ≥1 genuine result
    FNO_READY_FOR_SMOKE: bool = True            # architecture + loss + metrics all verified
    FNO_ACTUALLY_TRAINED: bool = False          # genuine training loop completed

    def __post_init__(self) -> None:
        self.validate_scientific_integrity()

    def validate_scientific_integrity(self) -> None:
        """Enforce non-negotiable scientific safety constraints."""
        if self.SUSCEPTIBILITY_IS_NOT_DEPTH is not True:
            raise ValueError("Susceptibility must never be treated as water depth")
        if self.REAL_PHYSICS_SIMULATION_EXECUTED and (
            not self.SWMM_INPUTS_AVAILABLE and not self.LISFLOOD_FP_INPUTS_AVAILABLE
        ):
            raise ValueError("Cannot claim simulation executed without physical inputs")
        if self.GENUINE_FNO_TARGETS_AVAILABLE and not self.REAL_PHYSICS_SIMULATION_EXECUTED:
            raise ValueError("Genuine FNO targets require executed real simulations")
        if self.FNO_TRAINING_STARTED and not self.GENUINE_FNO_TARGETS_AVAILABLE:
            raise ValueError("FNO training cannot start without genuine targets")
        if self.CITIZEN_REAL_ML_AVAILABLE and not self.CITIZEN_VERIFICATION_FOUNDATION_READY:
            raise ValueError("Citizen ML claim requires underlying verification foundation")
        if self.LOCKED_TEST_TOUCHED:
            raise PermissionError("Locked rainfall test set must remain untouched")
        if self.FABRICATED_DEPTH_USED or self.FAKE_PHYSICS_TRUTH_USED:
            raise ValueError("Fabrication of hydraulic depth or physics truth is strictly prohibited")

        # Phase 7 specific empirical validations
        if self.ROUGHNESS_CALIBRATED:
            raise ValueError("Roughness layer is uncalibrated literature parameterization; cannot claim calibration")
        if self.MUNICIPAL_DRAINAGE_NETWORK_AVAILABLE:
            raise ValueError("Municipal stormwater drainage network data is not present in repository")
        if self.SWMM_INPUTS_AVAILABLE and not self.MUNICIPAL_DRAINAGE_NETWORK_AVAILABLE:
            raise ValueError("SWMM inputs cannot be marked available without municipal drainage network")
        if self.SWMM_EXECUTION_READY and not self.SWMM_INPUTS_AVAILABLE:
            raise ValueError("SWMM execution cannot be ready without available inputs")
        if self.LISFLOOD_EXECUTION_READY and not self.LISFLOOD_SOLVER_AVAILABLE:
            raise ValueError("LISFLOOD-FP execution cannot be ready without solver binary")
        if self.GENUINE_POPULATION_DATA_AVAILABLE:
            raise ValueError("Census population raster is not present in local data repository")
        if self.REAL_FLOOD_VALIDATION_DATA_AVAILABLE:
            raise ValueError("Empirical flood validation extent is not present in local repository")
        if self.REAL_VULNERABILITY_DATA_AVAILABLE:
            raise ValueError("Socioeconomic vulnerability data is proxy only; cannot claim real census survey")

        # Phase 9 physics-execution integrity
        if self.LISFLOOD_SMOKE_EXECUTED and not self.LISFLOOD_EXECUTABLE:
            raise ValueError("Cannot claim smoke execution without solver binary on PATH")
        if self.GENUINE_SOLVER_OUTPUT_AVAILABLE and not self.LISFLOOD_SMOKE_EXECUTED:
            raise ValueError("Genuine solver output requires at least one executed smoke run")
        if self.PHYSICS_DATASET_READY and not self.GENUINE_SOLVER_OUTPUT_AVAILABLE:
            raise ValueError("Physics dataset requires genuine solver output")
        if self.FNO_ACTUALLY_TRAINED and not self.PHYSICS_DATASET_READY:
            raise ValueError("FNO training requires a frozen genuine physics dataset")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write_manifest(self, destination: str | Path) -> None:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


AUTHORITATIVE_GATES = ScientificClaimGates()
