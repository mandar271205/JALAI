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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write_manifest(self, destination: str | Path) -> None:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


AUTHORITATIVE_GATES = ScientificClaimGates()
