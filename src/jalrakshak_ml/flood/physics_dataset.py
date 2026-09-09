"""Leakage-safe manifest builder for genuine hydraulic reference outputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .physics import PhysicsResult, PhysicsScenario


def freeze_physics_dataset(
    scenarios: list[PhysicsScenario],
    results: list[PhysicsResult],
    split_by_scenario: dict[str, str],
    output_path: str | Path,
) -> dict[str, Any]:
    """Freeze an immutable scenario-level dataset; heuristic targets are rejected."""
    output = Path(output_path)
    if output.exists():
        raise FileExistsError("Physics dataset manifest is immutable")
    result_by_id = {result.scenario_id: result for result in results}
    if len(result_by_id) != len(results):
        raise ValueError("Duplicate physics result scenario")
    scenario_ids = {scenario.scenario_id for scenario in scenarios}
    if scenario_ids != set(result_by_id) or scenario_ids != set(split_by_scenario):
        raise ValueError("Scenario/result/split identities must match exactly")
    if set(split_by_scenario.values()) - {"train", "validation", "test"}:
        raise ValueError("Invalid physics dataset split")

    records = []
    for scenario in scenarios:
        result = result_by_id[scenario.scenario_id]
        result.validate()
        if result.metadata.get("target_source") in {
            "susceptibility",
            "heuristic",
            "random_synthetic",
        }:
            raise ValueError("FNO target is not genuine physics output")
        records.append(
            {
                "scenario_id": scenario.scenario_id,
                "split": split_by_scenario[scenario.scenario_id],
                "rainfall_event": scenario.provenance.get("rainfall_event"),
                "rainfall_source": scenario.provenance.get("rainfall_source"),
                "solver": result.solver,
                "solver_version": result.solver_version,
                "scenario_hash": scenario.stable_hash(),
                "parameter_set": {
                    "boundary_conditions": scenario.boundary_conditions,
                    "infiltration_parameters": scenario.infiltration_parameters,
                    "assumed_parameters": list(scenario.assumed_parameters),
                },
                "input_hashes": result.input_hashes,
                "output_hashes": result.output_hashes,
                "crs": scenario.crs,
                "timestep_minutes": scenario.temporal_resolution_minutes,
                "grid_shape": list(scenario.grid_shape),
                "target_units": result.depth_units,
                "convergence": result.convergence,
                "depth_timeseries_path": result.depth_timeseries_path,
                "valid_mask_path": result.valid_mask_path,
                "physics_reference": True,
                "physically_simulated": True,
                "calibrated": result.calibrated,
            }
        )
    manifest = {
        "dataset_version": "phase5_physics_reference_v1",
        "status": "FROZEN",
        "target_quantity": "physics_simulated_water_depth",
        "target_units": "m",
        "physics_reference": True,
        "records": records,
        "split_unit": "scenario_id",
        "susceptibility_used_as_depth_truth": False,
        "synthetic_depth_used": False,
    }
    encoded = json.dumps(manifest, sort_keys=True, allow_nan=False).encode()
    manifest["manifest_content_sha256"] = hashlib.sha256(encoded).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_suffix(output.suffix + ".part")
    part.write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    part.replace(output)
    return manifest
