"""Leakage-safe manifest builder for genuine hydraulic reference outputs.

Enforces mandatory integrity gates:
- REAL_SOLVER_OUTPUT=True
- solver_status=SUCCESS/EXECUTED
- fabricated_depth=False
- synthetic_target=False
- event-level split isolation (perturbations of the same event cannot cross splits)
- absolute rejection of susceptibility or heuristic risk as depth targets
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .physics import PhysicsResult, PhysicsScenario


class PhysicsDatasetBuilder:
    """Builder that validates scenario-result pairs and enforces event-level leakage isolation."""

    def __init__(self) -> None:
        self.scenarios: dict[str, PhysicsScenario] = {}
        self.results: dict[str, PhysicsResult] = {}
        self.splits: dict[str, str] = {}

    def add_entry(self, scenario: PhysicsScenario, result: PhysicsResult, split: str) -> None:
        if split not in {"train", "validation", "test"}:
            raise ValueError(f"Invalid split: {split}. Must be train, validation, or test.")
        scenario.validate(result.solver)
        result.validate()

        if result.scenario_id != scenario.scenario_id:
            raise ValueError("Scenario ID mismatch between scenario and result")
        if not result.physically_simulated:
            raise ValueError("Result is not physically simulated")

        target_source = result.metadata.get("target_source", "")
        if target_source in {"susceptibility", "heuristic", "random_synthetic", "synthetic"}:
            raise ValueError(f"Target source '{target_source}' is not genuine physics output")

        self.scenarios[scenario.scenario_id] = scenario
        self.results[scenario.scenario_id] = result
        self.splits[scenario.scenario_id] = split

    def validate_event_isolation(self) -> None:
        """Verify that all scenarios derived from the same base event are in the same split."""
        event_to_splits: dict[str, set[str]] = {}
        for scen_id, scen in self.scenarios.items():
            event = scen.provenance.get("rainfall_event") or scen.provenance.get("base_event")
            if event:
                event_to_splits.setdefault(event, set()).add(self.splits[scen_id])

        leaked_events = {event: splits for event, splits in event_to_splits.items() if len(splits) > 1}
        if leaked_events:
            raise ValueError(
                f"Data leakage detected across splits for events: {leaked_events}. "
                "All perturbations of an event must belong to the same split."
            )

    def freeze(self, output_path: str | Path) -> dict[str, Any]:
        self.validate_event_isolation()
        return freeze_physics_dataset(
            list(self.scenarios.values()),
            list(self.results.values()),
            self.splits,
            output_path,
        )


def freeze_physics_dataset(
    scenarios: list[PhysicsScenario],
    results: list[PhysicsResult],
    split_by_scenario: dict[str, str],
    output_path: str | Path,
) -> dict[str, Any]:
    """Freeze an immutable scenario-level dataset; heuristic/synthetic targets are rejected."""
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

    # Verify event-level leakage isolation
    event_splits: dict[str, set[str]] = {}
    for scenario in scenarios:
        event = scenario.provenance.get("rainfall_event") or scenario.provenance.get("base_event")
        if event:
            event_splits.setdefault(event, set()).add(split_by_scenario[scenario.scenario_id])
    leaked = {event: s for event, s in event_splits.items() if len(s) > 1}
    if leaked:
        raise ValueError(
            f"Event-level leakage detected: {leaked}. Perturbations of the same event must share a split."
        )

    records = []
    for scenario in scenarios:
        result = result_by_id[scenario.scenario_id]
        result.validate()

        # Hard gate against heuristic or synthetic depth
        target_src = result.metadata.get("target_source", "")
        if target_src in {"susceptibility", "heuristic", "random_synthetic", "synthetic"}:
            raise ValueError("FNO target is not genuine physics output")
        if not result.physically_simulated:
            raise ValueError("Target depth was not physically simulated")

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
