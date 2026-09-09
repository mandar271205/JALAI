"""Validate hydraulic physics inputs and solver availability without fabrication."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from jalrakshak_ml.flood.physics import ExecutionStatus


def validate_physics_environment(
    dem_path: Path,
    roughness_path: Path,
    rainfall_path: Path,
    drainage_path: Path | None = None,
    solver: str = "SWMM",
) -> dict[str, Any]:
    issues: list[str] = []
    inputs_status = ExecutionStatus.READY

    if not dem_path.is_file():
        issues.append(f"DEM raster missing: {dem_path}")
        inputs_status = ExecutionStatus.BLOCKED_MISSING_INPUT
    if not roughness_path.is_file():
        issues.append(f"Manning roughness raster missing: {roughness_path}")
        inputs_status = ExecutionStatus.BLOCKED_MISSING_INPUT
    if not rainfall_path.is_file():
        issues.append(f"Rainfall forcing file missing: {rainfall_path}")
        inputs_status = ExecutionStatus.BLOCKED_MISSING_INPUT

    if solver == "SWMM":
        if not drainage_path or not drainage_path.is_file():
            issues.append(f"SWMM requires genuine municipal drainage network .inp file: {drainage_path}")
            inputs_status = ExecutionStatus.BLOCKED_MISSING_INPUT
        exe = shutil.which("swmm5") or shutil.which("swmm")
    elif solver == "LISFLOOD-FP":
        exe = shutil.which("lisflood")
    else:
        exe = None
        issues.append(f"Unsupported solver: {solver}")

    solver_status = ExecutionStatus.READY if exe else ExecutionStatus.BLOCKED_MISSING_SOLVER
    if not exe:
        issues.append(f"Solver executable for {solver} not found on system PATH")

    overall_status = (
        ExecutionStatus.READY
        if inputs_status == ExecutionStatus.READY and solver_status == ExecutionStatus.READY
        else inputs_status
        if inputs_status != ExecutionStatus.READY
        else solver_status
    )

    report = {
        "solver": solver,
        "overall_status": overall_status.value,
        "inputs_status": inputs_status.value,
        "solver_binary_status": solver_status.value,
        "solver_executable": exe,
        "inputs": {
            "dem": str(dem_path),
            "dem_exists": dem_path.is_file(),
            "roughness": str(roughness_path),
            "roughness_exists": roughness_path.is_file(),
            "rainfall": str(rainfall_path),
            "rainfall_exists": rainfall_path.is_file(),
            "drainage": str(drainage_path) if drainage_path else None,
            "drainage_exists": drainage_path.is_file() if drainage_path else False,
        },
        "issues": issues,
        "physically_simulated": False,
        "fake_depth_allowed": False,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem", type=Path, default=Path("data/processed/static/elevation.tif"))
    parser.add_argument("--roughness", type=Path, default=Path("data/processed/static/slope.tif"))
    parser.add_argument("--rainfall", type=Path, default=Path("data/processed/rainfall_sample.npy"))
    parser.add_argument("--drainage", type=Path, default=None)
    parser.add_argument("--solver", choices=["SWMM", "LISFLOOD-FP"], default="SWMM")
    parser.add_argument("--output", type=Path, default=Path("reports/phase5_physics_validation.json"))
    args = parser.parse_args()

    report = validate_physics_environment(
        args.dem,
        args.roughness,
        args.rainfall,
        args.drainage,
        args.solver,
    )
    print(json.dumps(report, indent=2))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Validation report saved to: {args.output}")


if __name__ == "__main__":
    main()
