from __future__ import annotations

import hashlib
import json
import subprocess

import numpy as np
import pytest
import torch

from jalrakshak_ml.explain.risk_explanation import RiskExplanation, format_risk_explanation
from jalrakshak_ml.flood.fno import (
    FloodFNO,
    FNOTrainingConfig,
    FNOTrainingRunner,
    require_physics_reference_dataset,
)
from jalrakshak_ml.flood.physics import (
    INSUFFICIENT_PHYSICAL_INPUTS,
    LISFLOODAdapter,
    PhysicsResult,
    PhysicsScenario,
    SWMMAdapter,
    rainfall_rate_to_interval_depth,
)
from jalrakshak_ml.flood.physics_dataset import freeze_physics_dataset
from jalrakshak_ml.flood.susceptibility import (
    FloodSusceptibilityEngine,
    RasterGrid,
    SusceptibilityFeature,
)
from jalrakshak_ml.risk.intelligence import (
    ExposureEngine,
    ExposureLayer,
    RiskMethodology,
    VulnerabilityFactor,
    propagate_scenarios,
    vulnerability_status,
)


def _grid():
    return RasterGrid("EPSG:32643", 2, 2, (200.0, 0.0, 0.0, 0.0, -200.0, 0.0))


def _feature(name="elevation", grid=None):
    return SusceptibilityFeature(
        name,
        np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32),
        grid or _grid(),
        "genuine-test-fixture",
        "a" * 64,
    )


def test_susceptibility_is_dimensionless_and_never_depth():
    result = FloodSusceptibilityEngine().score([_feature()], {"elevation": 1.0})
    assert result.metadata["calibrated_depth"] is False
    assert result.metadata["units"] == "dimensionless"
    with pytest.raises(PermissionError, match="not physics-derived"):
        result.refuse_depth_export("depth_m")


def test_susceptibility_alignment_is_strict():
    wrong_grid = RasterGrid("EPSG:4326", 2, 2, (0.1, 0.0, 0.0, 0.0, -0.1, 0.0))
    with pytest.raises(ValueError, match="share CRS"):
        FloodSusceptibilityEngine().score(
            [_feature(), _feature("slope", wrong_grid)],
            {"elevation": 0.5, "slope": 0.5},
        )


def _scenario(tmp_path):
    paths = {}
    for name in ("rain.npy", "dem.tif", "roughness.tif", "network.inp"):
        path = tmp_path / name
        path.write_bytes(b"genuine fixture")
        paths[name] = str(path)
    return PhysicsScenario(
        "scenario-1",
        paths["rain.npy"],
        "mm/h",
        "2024-01-01T00:00:00+00:00",
        "2024-01-01T02:00:00+00:00",
        30,
        paths["dem.tif"],
        paths["roughness.tif"],
        paths["network.inp"],
        {"downstream": "open"},
        {"method": "declared-test"},
        "EPSG:32643",
        (2, 2),
        {"rainfall_source": "genuine-test-fixture", "rainfall_event": "event-1"},
        ("roughness:test-only",),
    )


def test_physics_contract_units_hash_and_missing_input(tmp_path):
    scenario = _scenario(tmp_path)
    scenario.validate("SWMM")
    assert len(scenario.stable_hash()) == 64
    np.testing.assert_allclose(rainfall_rate_to_interval_depth(np.array([2.0]), 30), [1.0])
    missing = PhysicsScenario(**{**scenario.__dict__, "dem_path": str(tmp_path / "missing")})
    with pytest.raises(FileNotFoundError, match=INSUFFICIENT_PHYSICAL_INPUTS):
        missing.validate("LISFLOOD-FP")


def test_solver_adapters_fail_without_executables(tmp_path):
    scenario = _scenario(tmp_path)
    with pytest.raises(FileNotFoundError, match="executable unavailable"):
        SWMMAdapter("definitely-not-installed-swmm").run(scenario, tmp_path / "out")
    with pytest.raises(FileNotFoundError, match="executable unavailable"):
        LISFLOODAdapter("definitely-not-installed-lisflood").run(scenario, tmp_path / "out")


def test_solver_timeout_and_failure_propagate(tmp_path, monkeypatch):
    scenario = _scenario(tmp_path)

    def timeout_runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    adapter = SWMMAdapter("mock-swmm", process_runner=timeout_runner)
    monkeypatch.setattr(adapter, "executable_path", lambda: "mock-swmm")
    with pytest.raises(TimeoutError, match="timed out"):
        adapter.run(scenario, tmp_path / "timeout", timeout=1)

    def failure_runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 2, "", "solver failure")

    adapter = SWMMAdapter("mock-swmm", process_runner=failure_runner)
    monkeypatch.setattr(adapter, "executable_path", lambda: "mock-swmm")
    with pytest.raises(RuntimeError, match="solver failure"):
        adapter.run(scenario, tmp_path / "failure")


def test_solver_rejects_malformed_or_mocked_parser_result(tmp_path, monkeypatch):
    scenario = _scenario(tmp_path)

    def success_runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, "", "")

    def fake_parser(scenario, output_root, runtime_seconds):
        del output_root
        return PhysicsResult(
            scenario.scenario_id,
            str(tmp_path / "missing-max.npy"),
            str(tmp_path / "missing-series.npy"),
            str(tmp_path / "missing-extent.npy"),
            None,
            str(tmp_path / "missing-mask.npy"),
            "SWMM",
            "test",
            runtime_seconds,
            "SUCCESS",
            "CONVERGED",
            {"input": "a" * 64},
            {"output": "b" * 64},
            False,
            False,
        )

    adapter = SWMMAdapter("mock-swmm", process_runner=success_runner, output_parser=fake_parser)
    monkeypatch.setattr(adapter, "executable_path", lambda: "mock-swmm")
    with pytest.raises(ValueError, match="not genuine"):
        adapter.run(scenario, tmp_path / "malformed")


def test_mock_or_heuristic_physics_cannot_be_truth(tmp_path):
    result = PhysicsResult(
        "scenario-1",
        str(tmp_path / "max.npy"),
        str(tmp_path / "series.npy"),
        str(tmp_path / "extent.npy"),
        None,
        str(tmp_path / "mask.npy"),
        "LISFLOOD-FP",
        "test",
        0.0,
        "SUCCESS",
        "CONVERGED",
        {"dem": "a" * 64},
        {"depth": "b" * 64},
        False,
        False,
    )
    with pytest.raises(ValueError, match="not genuine"):
        result.validate()


def test_physics_dataset_rejects_heuristic_depth(tmp_path):
    scenario = _scenario(tmp_path)
    output_paths = []
    for name in ("max.npy", "series.npy", "extent.npy", "mask.npy"):
        path = tmp_path / name
        path.write_bytes(b"physics fixture")
        output_paths.append(str(path))
    result = PhysicsResult(
        "scenario-1",
        output_paths[0],
        output_paths[1],
        output_paths[2],
        None,
        output_paths[3],
        "LISFLOOD-FP",
        "test",
        1.0,
        "SUCCESS",
        "CONVERGED",
        {"dem": "a" * 64},
        {"depth": "b" * 64},
        True,
        False,
        metadata={"target_source": "susceptibility"},
    )
    with pytest.raises(ValueError, match="not genuine physics"):
        freeze_physics_dataset(
            [scenario],
            [result],
            {"scenario-1": "train"},
            tmp_path / "dataset.json",
        )


def test_fno_shape_nonnegative_and_training_provenance_gate(tmp_path):
    model = FloodFNO(3, width=4, modes=2)
    with torch.no_grad():
        output = model(torch.rand(2, 3, 8, 8))
    assert output.shape == (2, 4, 1, 8, 8)
    assert torch.all(output >= 0)
    manifest = tmp_path / "physics.json"
    manifest.write_text(
        json.dumps({"status": "FROZEN", "physics_reference": False}), encoding="utf-8"
    )
    with pytest.raises(PermissionError, match="genuine physics"):
        require_physics_reference_dataset(manifest)


def test_fno_runner_requires_train_only_normalization_and_saves_atomic_checkpoint(tmp_path):
    physics = {
        "dataset_version": "phase5_physics_reference_v1",
        "status": "FROZEN",
        "target_quantity": "physics_simulated_water_depth",
        "physics_reference": True,
        "records": [
            {
                "scenario_id": "train-1",
                "split": "train",
                "physically_simulated": True,
                "physics_reference": True,
            },
            {
                "scenario_id": "validation-1",
                "split": "validation",
                "physically_simulated": True,
                "physics_reference": True,
            },
        ],
    }
    physics["manifest_content_sha256"] = hashlib.sha256(
        json.dumps(physics, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    physics_path = tmp_path / "physics.json"
    physics_path.write_text(json.dumps(physics), encoding="utf-8")
    normalization = {
        "normalization_version": "phase5_fno_train_only_v1",
        "status": "PASS",
        "fitted_split": "train",
        "fitted_scenario_ids": ["train-1"],
        "channel_order": ["rainfall", "elevation", "roughness"],
        "input_statistics": {
            name: {"mean": 0.0, "std": 1.0} for name in ("rainfall", "elevation", "roughness")
        },
        "validation_opened": False,
        "test_opened": False,
    }
    normalization_path = tmp_path / "normalization.json"
    normalization_path.write_text(json.dumps(normalization), encoding="utf-8")
    runner = FNOTrainingRunner(
        physics_path,
        normalization_path,
        config=FNOTrainingConfig(),
        git_commit="a" * 40,
    )
    model = FloodFNO(3, width=4, modes=2)
    loss = runner.training_step(
        model,
        torch.rand(1, 3, 8, 8),
        torch.rand(1, 4, 1, 8, 8),
        torch.ones(1, 4, 1, 8, 8, dtype=torch.bool),
    )
    assert torch.isfinite(loss)
    optimizer = torch.optim.AdamW(model.parameters())
    payload = runner.checkpoint_payload(
        model, optimizer, epoch=1, validation_metrics={"depth_mae_m": 0.1}
    )
    checkpoint = tmp_path / "fno.pt"
    runner.save_checkpoint_atomic(payload, checkpoint)
    assert checkpoint.is_file() and not checkpoint.with_suffix(".pt.part").exists()


def test_exposure_vulnerability_and_risk_stay_separate():
    layer = ExposureLayer(
        "population",
        "population",
        "raster",
        "EPSG:32643",
        "genuine-test-fixture",
        "v1",
        "a" * 64,
        np.ones((2, 2), dtype=np.float32),
    )
    exposure = ExposureEngine().intersect_raster(
        np.array([[0.0, 1.0], [0.0, 2.0]]), layer, hazard_crs="EPSG:32643", threshold=0.5
    )
    assert exposure["exposed_cell_count"] == 2 and exposure["invented_counts"] is False
    status = vulnerability_status([VulnerabilityFactor("building", None, "fraction", None)])
    assert status["status"] == "PARTIAL"
    risk = RiskMethodology("v1", (0, 2), (0, 10)).evaluate(
        hazard=1,
        exposure=5,
        vulnerability=0.5,
        provenance={"hazard": "fixture", "exposure": "fixture", "vulnerability": "fixture"},
        data_quality="TEST_FIXTURE",
        model_confidence=None,
    )
    assert risk["raw_risk_score"] == pytest.approx(0.125)
    assert risk["data_quality"] == "TEST_FIXTURE"


def test_uncertainty_and_explanation_keep_quality_distinct():
    uncertainty = propagate_scenarios(
        np.array([[0.0], [1.0]]), np.array([0.25, 0.75]), calibrated=False
    )
    assert uncertainty["calibrated_probability"] is False
    explanation = RiskExplanation(
        {"rainfall": 0.5},
        {"susceptibility": 0.4, "calibrated_depth": False},
        {"assets": 2},
        {"factor": 0.3},
        uncertainty,
        {"status": "PARTIAL"},
        ("No calibrated depth",),
        {"risk": "v1"},
        {"rainfall": "fixture"},
    )
    text = format_risk_explanation(explanation)
    assert "No calibrated depth" in text
