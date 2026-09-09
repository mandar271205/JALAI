"""Reproducible contracts, execution gates, and fail-closed adapters for hydraulic solvers.

Never fabricates hydraulic outputs, drainage networks, or flood depths.
"""

from __future__ import annotations

import enum
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

INSUFFICIENT_PHYSICAL_INPUTS = "INSUFFICIENT_PHYSICAL_INPUTS"


class ExecutionStatus(str, enum.Enum):
    READY = "READY"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    BLOCKED_MISSING_INPUT = "BLOCKED_MISSING_INPUT"
    BLOCKED_MISSING_SOLVER = "BLOCKED_MISSING_SOLVER"


class PhysicsRunMode(str, enum.Enum):
    DRY_RUN = "DRY_RUN"
    VALIDATION_ONLY = "VALIDATION_ONLY"
    EXECUTE = "EXECUTE"


@dataclass(frozen=True)
class PhysicsScenario:
    scenario_id: str
    rainfall_forcing_path: str
    rainfall_units: str
    start_time: str
    end_time: str
    temporal_resolution_minutes: int
    dem_path: str
    roughness_path: str
    drainage_network_path: str | None
    boundary_conditions: dict[str, Any]
    infiltration_parameters: dict[str, Any]
    crs: str
    grid_shape: tuple[int, int]
    provenance: dict[str, Any]
    assumed_parameters: tuple[str, ...] = ()

    def validate(self, solver: str) -> None:
        if not self.scenario_id or self.rainfall_units != "mm/h":
            raise ValueError("Scenario id and rainfall units mm/h are required")
        if self.temporal_resolution_minutes <= 0 or not self.crs.startswith("EPSG:"):
            raise ValueError("Scenario timestep and CRS are invalid")
        if len(self.grid_shape) != 2 or min(self.grid_shape) < 1:
            raise ValueError("Scenario grid shape is invalid")
        try:
            start = datetime.fromisoformat(self.start_time)
            end = datetime.fromisoformat(self.end_time)
        except ValueError as error:
            raise ValueError("Scenario start/end timestamps must be ISO-8601") from error
        if end <= start:
            raise ValueError("Scenario end time must be after start time")
        required = [self.rainfall_forcing_path, self.dem_path, self.roughness_path]
        if solver == "SWMM":
            if not self.drainage_network_path:
                raise FileNotFoundError(f"{INSUFFICIENT_PHYSICAL_INPUTS}: SWMM drainage network path missing")
            required.append(self.drainage_network_path)
        missing = [path for path in required if not path or not Path(path).is_file()]
        if missing:
            raise FileNotFoundError(f"{INSUFFICIENT_PHYSICAL_INPUTS}: {missing}")
        if not self.boundary_conditions or not self.infiltration_parameters:
            raise ValueError(
                f"{INSUFFICIENT_PHYSICAL_INPUTS}: explicit physical parameters required"
            )
        if not self.provenance or self.provenance.get("synthetic", False):
            raise ValueError("Genuine input provenance is required")

    def stable_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def check_execution_readiness(
        self, solver: str, executable_name: str | None = None
    ) -> tuple[ExecutionStatus, str]:
        """Check status without raising, returning explicit status and reason."""
        try:
            self.validate(solver)
        except (FileNotFoundError, ValueError) as err:
            return ExecutionStatus.BLOCKED_MISSING_INPUT, str(err)

        exe = executable_name or ("swmm5" if solver == "SWMM" else "lisflood")
        if not shutil.which(exe):
            return (
                ExecutionStatus.BLOCKED_MISSING_SOLVER,
                f"{solver} binary '{exe}' is not installed on PATH",
            )
        return ExecutionStatus.READY, "All physical inputs and solver binary verified"


@dataclass(frozen=True)
class PhysicsResult:
    scenario_id: str
    max_depth_path: str
    depth_timeseries_path: str
    inundation_extent_path: str
    velocity_path: str | None
    valid_mask_path: str
    solver: str
    solver_version: str
    runtime_seconds: float
    status: str
    convergence: str
    input_hashes: dict[str, str]
    output_hashes: dict[str, str]
    physically_simulated: bool
    calibrated: bool
    depth_units: str = "m"
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.status != "SUCCESS" or self.convergence != "CONVERGED":
            raise RuntimeError("Physics result did not complete successfully")
        if not self.physically_simulated:
            raise ValueError("A mocked or heuristic result is not genuine physics truth")
        if self.depth_units != "m" or self.runtime_seconds < 0:
            raise ValueError("Depth units/runtime are invalid")
        required = [
            self.max_depth_path,
            self.depth_timeseries_path,
            self.inundation_extent_path,
            self.valid_mask_path,
        ]
        if any(not Path(path).is_file() for path in required):
            raise FileNotFoundError("Physics output artifact missing")
        if not self.input_hashes or not self.output_hashes:
            raise ValueError("Physics input/output hashes are required")

    def write_metadata_atomic(self, destination: str | Path) -> None:
        path = Path(destination)
        if path.exists():
            raise FileExistsError("Physics metadata is immutable")
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(path.suffix + ".part")
        part.write_text(json.dumps(asdict(self), indent=2, allow_nan=False), encoding="utf-8")
        part.replace(path)


def rainfall_rate_to_interval_depth(
    rainfall_mm_h: np.ndarray, temporal_resolution_minutes: int
) -> np.ndarray:
    """Convert rate forcing to interval depth without changing its physical meaning."""
    values = np.asarray(rainfall_mm_h, dtype=np.float64)
    if temporal_resolution_minutes <= 0 or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Valid nonnegative rainfall rate and timestep are required")
    return values * temporal_resolution_minutes / 60.0


ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]
OutputParser = Callable[[PhysicsScenario, Path, float], PhysicsResult]


class SolverAdapter:
    solver_name = "UNSPECIFIED"

    def __init__(
        self,
        executable: str,
        *,
        process_runner: ProcessRunner = subprocess.run,
        output_parser: OutputParser | None = None,
    ):
        self.executable = executable
        self.process_runner = process_runner
        self.output_parser = output_parser

    def executable_path(self) -> str:
        located = shutil.which(self.executable)
        if not located:
            raise FileNotFoundError(f"{self.solver_name} executable unavailable: {self.executable}")
        return located

    def validate_only(self, scenario: PhysicsScenario) -> dict[str, Any]:
        """Perform non-modifying input and environment validation."""
        status, reason = scenario.check_execution_readiness(self.solver_name, self.executable)
        return {
            "scenario_id": scenario.scenario_id,
            "solver": self.solver_name,
            "status": status.value,
            "reason": reason,
            "scenario_hash": scenario.stable_hash(),
        }

    def dry_run(self, scenario: PhysicsScenario, output_root: str | Path) -> dict[str, Any]:
        """Verify command construction and inputs without executing the solver."""
        scenario.validate(self.solver_name)
        exe = self.executable_path()
        output_root = Path(output_root)
        dummy_work = Path("/tmp/jalai_dryrun")
        command = self.build_command(exe, scenario, dummy_work, output_root)
        return {
            "scenario_id": scenario.scenario_id,
            "solver": self.solver_name,
            "dry_run": True,
            "command": command,
            "executable": exe,
            "scenario_hash": scenario.stable_hash(),
            "status": ExecutionStatus.READY.value,
        }

    def run(
        self,
        scenario: PhysicsScenario,
        output_root: str | Path,
        *,
        timeout: int = 3600,
        mode: PhysicsRunMode = PhysicsRunMode.EXECUTE,
    ) -> PhysicsResult:
        """Execute in an isolated work directory; genuine parsing is subclass-specific."""
        if mode == PhysicsRunMode.VALIDATION_ONLY:
            report = self.validate_only(scenario)
            raise RuntimeError(f"Validation-only mode requested: {report}")
        if mode == PhysicsRunMode.DRY_RUN:
            report = self.dry_run(scenario, output_root)
            raise RuntimeError(f"Dry-run mode requested: {report}")

        scenario.validate(self.solver_name)
        executable = self.executable_path()
        output_root = Path(output_root)
        output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"jalai_{self.solver_name.lower()}_") as work:
            command = self.build_command(executable, scenario, Path(work), output_root)
            started = time.perf_counter()
            try:
                completed = self.process_runner(
                    command,
                    cwd=work,
                    timeout=timeout,
                    check=False,
                    capture_output=True,
                    text=True,
                )
            except subprocess.TimeoutExpired as error:
                raise TimeoutError(f"{self.solver_name} timed out after {timeout}s") from error
            if completed.returncode != 0:
                raise RuntimeError(
                    f"{self.solver_name} failed ({completed.returncode}): {completed.stderr[-1000:]}"
                )
            result = self.parse_outputs(scenario, output_root, time.perf_counter() - started)
            if result.scenario_id != scenario.scenario_id or result.solver != self.solver_name:
                raise ValueError("Parsed physics result identity/solver mismatch")
            result.validate()
            return result

    def build_command(
        self, executable: str, scenario: PhysicsScenario, work_dir: Path, output_root: Path
    ) -> list[str]:
        raise NotImplementedError

    def parse_outputs(
        self, scenario: PhysicsScenario, output_root: Path, runtime_seconds: float
    ) -> PhysicsResult:
        raise NotImplementedError


class SWMMAdapter(SolverAdapter):
    solver_name = "SWMM"

    def build_command(self, executable, scenario, work_dir, output_root):
        del work_dir
        if scenario.drainage_network_path is None:
            raise ValueError(f"{INSUFFICIENT_PHYSICAL_INPUTS}: SWMM network")
        return [
            executable,
            scenario.drainage_network_path,
            str(output_root / "swmm.rpt"),
            str(output_root / "swmm.out"),
        ]

    def parse_outputs(self, scenario, output_root, runtime_seconds):
        if self.output_parser is None:
            raise RuntimeError("A real SWMM output parser is required")
        return self.output_parser(scenario, output_root, runtime_seconds)


class LISFLOODAdapter(SolverAdapter):
    solver_name = "LISFLOOD-FP"

    def build_command(self, executable, scenario, work_dir, output_root):
        del work_dir
        parameter_file = output_root / "lisflood.par"
        if not parameter_file.is_file():
            raise FileNotFoundError(f"{INSUFFICIENT_PHYSICAL_INPUTS}: {parameter_file}")
        return [executable, str(parameter_file)]

    def parse_outputs(self, scenario, output_root, runtime_seconds):
        if self.output_parser is None:
            raise RuntimeError("A real LISFLOOD-FP output parser is required")
        return self.output_parser(scenario, output_root, runtime_seconds)
