"""Execute or dry-run hydraulic physics scenarios using fail-closed adapters."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jalrakshak_ml.flood.physics import (
    ExecutionStatus,
    LISFLOODAdapter,
    PhysicsRunMode,
    PhysicsScenario,
    SWMMAdapter,
)


def run_scenarios(
    scenario_manifest_path: Path,
    output_root: Path,
    solver: str = "SWMM",
    mode: PhysicsRunMode = PhysicsRunMode.DRY_RUN,
) -> dict[str, Any]:
    manifest = json.loads(scenario_manifest_path.read_text(encoding="utf-8"))
    scenarios_data = manifest.get("scenarios", [])
    if not scenarios_data:
        raise ValueError(f"No scenarios found in {scenario_manifest_path}")

    results: list[dict[str, Any]] = []
    overall_status = ExecutionStatus.READY

    adapter = SWMMAdapter("swmm5") if solver == "SWMM" else LISFLOODAdapter("lisflood")

    for item in scenarios_data:
        scen = PhysicsScenario(
            scenario_id=item["scenario_id"],
            rainfall_forcing_path=item["rainfall_forcing_path"],
            rainfall_units=item["rainfall_units"],
            start_time=item.get("start_time", "2024-01-01T00:00:00+00:00"),
            end_time=item.get("end_time", "2024-01-01T02:00:00+00:00"),
            temporal_resolution_minutes=item.get("temporal_resolution_minutes", 30),
            dem_path=item.get("dem_path", "data/processed/static/elevation.tif"),
            roughness_path=item.get("roughness_path", "data/processed/static/slope.tif"),
            drainage_network_path=item.get("drainage_network_path"),
            boundary_conditions=item.get("boundary_conditions", {"downstream": "open"}),
            infiltration_parameters=item.get("infiltration_parameters", {"method": "Horton"}),
            crs=item["crs"],
            grid_shape=tuple(item["grid_shape"]),
            provenance={"source": "manifest", "scenario_family": item.get("scenario_family", "unknown")},
        )

        readiness, reason = scen.check_execution_readiness(solver)
        if readiness != ExecutionStatus.READY:
            results.append({
                "scenario_id": scen.scenario_id,
                "status": readiness.value,
                "reason": reason,
                "executed": False,
            })
            if overall_status == ExecutionStatus.READY:
                overall_status = readiness
            continue

        if mode == PhysicsRunMode.VALIDATION_ONLY:
            val_report = adapter.validate_only(scen)
            results.append({**val_report, "executed": False})
        elif mode == PhysicsRunMode.DRY_RUN:
            dry_report = adapter.dry_run(scen, output_root / scen.scenario_id)
            results.append({**dry_report, "executed": False})
        else:
            # Execution mode
            res = adapter.run(scen, output_root / scen.scenario_id)
            results.append({
                "scenario_id": scen.scenario_id,
                "status": ExecutionStatus.EXECUTED.value,
                "runtime_seconds": res.runtime_seconds,
                "executed": True,
            })

    return {
        "status": overall_status.value,
        "mode": mode.value,
        "solver": solver,
        "scenario_count": len(scenarios_data),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/processed/flood/physics_scenarios_v1.json"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/flood/physics_runs_v1"))
    parser.add_argument("--solver", choices=["SWMM", "LISFLOOD-FP"], default="SWMM")
    parser.add_argument("--mode", choices=["DRY_RUN", "VALIDATION_ONLY", "EXECUTE"], default="DRY_RUN")
    parser.add_argument("--output-audit", type=Path, default=Path("reports/phase5_physics_execution_audit.json"))
    args = parser.parse_args()

    if not args.manifest.is_file():
        # Write clean, fail-safe report if manifest is not yet generated
        report = {
            "status": ExecutionStatus.BLOCKED_MISSING_INPUT.value,
            "reason": f"Scenario manifest not found: {args.manifest}",
            "executed": False,
        }
    else:
        report = run_scenarios(
            args.manifest,
            args.output_root,
            solver=args.solver,
            mode=PhysicsRunMode(args.mode),
        )

    print(json.dumps(report, indent=2))
    args.output_audit.parent.mkdir(parents=True, exist_ok=True)
    args.output_audit.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report written to: {args.output_audit}")


if __name__ == "__main__":
    main()
