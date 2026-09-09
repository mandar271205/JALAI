"""Comprehensive verification test suite for the research-grade Flood Intelligence and Risk stack."""

from __future__ import annotations

import numpy as np
import pytest
import torch

from jalrakshak_ml.benchmark.final_harness import FinalBenchmarkHarness
from jalrakshak_ml.citizen.verification import (
    CitizenReport,
    CitizenReportVerificationEngine,
    VerificationStatus,
)
from jalrakshak_ml.core.claim_gates import ScientificClaimGates
from jalrakshak_ml.explain.risk_explanation import (
    ExplainabilityEngine,
    format_risk_explanation,
)
from jalrakshak_ml.flood.fno import (
    FloodFNO,
    SparseFloodLoss,
    evaluate_fno,
)
from jalrakshak_ml.flood.physics import (
    ExecutionStatus,
    PhysicsResult,
    PhysicsScenario,
    SWMMAdapter,
)
from jalrakshak_ml.flood.physics_dataset import PhysicsDatasetBuilder
from jalrakshak_ml.flood.scenario_generator import ScenarioFamily, ScenarioGenerator
from jalrakshak_ml.flood.susceptibility import (
    FloodSusceptibilityEngine,
    LayerPolicy,
    RasterGrid,
    SusceptibilityCategory,
    SusceptibilityFeature,
    compute_low_lying_index,
    compute_slope,
)
from jalrakshak_ml.risk.exposure import AdvancedExposureEngine, AssetClass, ExposureAssetLayer
from jalrakshak_ml.risk.intelligence import (
    ProbabilisticHEVRiskEngine,
    RiskCategory,
    RiskMethodology,
)
from jalrakshak_ml.risk.uncertainty import UncertaintyPropagator
from jalrakshak_ml.risk.vulnerability import (
    VULNERABILITY_DATA_INSUFFICIENT,
    SourcedVulnerabilityFactor,
    VulnerabilityDimension,
    VulnerabilityEngine,
)

# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------


def _dummy_grid(width=4, height=4):
    return RasterGrid("EPSG:32643", width, height, (100.0, 0.0, 0.0, 0.0, -100.0, 0.0))


def _dummy_feature(name="elevation", arr=None, grid=None):
    g = grid or _dummy_grid()
    val = arr if arr is not None else np.arange(g.height * g.width, dtype=np.float32).reshape(g.height, g.width)
    return SusceptibilityFeature(
        name=name,
        values=val,
        grid=g,
        source="copernicus_test",
        source_sha256="0" * 64,
        source_resolution=(100.0, 100.0),
    )


# ---------------------------------------------------------------------------
# 1. SUSCEPTIBILITY TESTS
# ---------------------------------------------------------------------------


def test_susceptibility_classification_and_range():
    grid = _dummy_grid(4, 4)
    elev = np.array([
        [10.0, 20.0, 30.0, 40.0],
        [50.0, 60.0, 70.0, 80.0],
        [90.0, 100.0, 110.0, 120.0],
        [130.0, 140.0, 150.0, 160.0],
    ], dtype=np.float32)

    feat = _dummy_feature("elevation", arr=elev, grid=grid)
    engine = FloodSusceptibilityEngine()
    res = engine.score([feat], {"elevation": 1.0})

    assert res.metadata["quantity"] == "relative_flood_susceptibility"
    assert res.metadata["units"] == "dimensionless"
    assert res.metadata["calibrated_depth"] is False
    assert (res.score >= 0.0).all() and (res.score <= 1.0).all()

    # Inverse ranking check: lowest elevation must have HIGHEST susceptibility score
    assert res.score[0, 0] > res.score[3, 3]

    # Categorical bins check
    cats = res.categorical_classes()
    assert cats.shape == (4, 4)
    assert cats[0, 0] == SusceptibilityCategory.VERY_HIGH.value
    assert cats[3, 3] == SusceptibilityCategory.VERY_LOW.value

    # Reject depth export
    with pytest.raises(PermissionError, match="not physics-derived"):
        res.refuse_depth_export("depth_m")


def test_susceptibility_layer_policy_enforcement():
    grid = _dummy_grid()
    f1 = _dummy_feature("elevation", grid=grid)

    engine = FloodSusceptibilityEngine()
    # Missing required layer raises ValueError
    with pytest.raises(ValueError, match="Required susceptibility layer is missing"):
        engine.score(
            [f1],
            {"elevation": 1.0},
            layer_policies={"distance_to_water": LayerPolicy.REQUIRED},
        )


def test_susceptibility_derivation_helpers():
    dem = np.array([
        [10.0, 12.0, 15.0],
        [8.0, 10.0, 14.0],
        [5.0, 7.0, 10.0],
    ], dtype=np.float32)

    slope = compute_slope(dem, 100.0, 100.0)
    assert slope.shape == (3, 3)
    assert np.isfinite(slope).all()
    assert (slope >= 0).all()

    low_lying = compute_low_lying_index(dem, kernel_radius=1)
    assert low_lying.shape == (3, 3)
    assert np.isfinite(low_lying).all()
    # The cell with elevation 5.0 (bottom-left) is lowest in its neighborhood
    assert low_lying[2, 0] > 0.0


# ---------------------------------------------------------------------------
# 2. PHYSICS ORCHESTRATION & SCENARIO GENERATION TESTS
# ---------------------------------------------------------------------------


def test_physics_scenario_generator_and_readiness(tmp_path):
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"dem_data")
    rough = tmp_path / "roughness.tif"
    rough.write_bytes(b"rough_data")
    rain = tmp_path / "rain.npy"
    rain.write_bytes(b"rain_data")

    gen = ScenarioGenerator(str(dem), str(rough), drainage_network_path=None)
    base = gen.generate_historical_scenario(
        event_id="2024-07-21",
        rainfall_path=str(rain),
        start_time="2024-07-21T00:00:00+00:00",
        end_time="2024-07-21T03:00:00+00:00",
    )
    assert base.provenance["is_observation"] is True
    assert base.provenance["scenario_family"] == ScenarioFamily.HISTORICAL_OBSERVED.value

    # Check execution readiness: SWMM blocked because drainage network is missing
    status, reason = base.check_execution_readiness("SWMM")
    assert status == ExecutionStatus.BLOCKED_MISSING_INPUT
    assert "SWMM drainage network" in reason

    # Generate perturbations
    perturbed = gen.generate_perturbed_scenarios(base, intensity_factors=(1.2,), temporal_shifts=(-30,))
    assert len(perturbed) == 2
    for p in perturbed:
        assert p.provenance["is_observation"] is False
        assert p.provenance["is_scenario_not_observation"] is True


def test_solver_dry_run_and_command_construction(tmp_path):
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"dem")
    rough = tmp_path / "rough.tif"
    rough.write_bytes(b"rough")
    rain = tmp_path / "rain.npy"
    rain.write_bytes(b"rain")
    drainage = tmp_path / "network.inp"
    drainage.write_bytes(b"inp")

    scen = PhysicsScenario(
        scenario_id="scen_test",
        rainfall_forcing_path=str(rain),
        rainfall_units="mm/h",
        start_time="2024-01-01T00:00:00+00:00",
        end_time="2024-01-01T01:00:00+00:00",
        temporal_resolution_minutes=30,
        dem_path=str(dem),
        roughness_path=str(rough),
        drainage_network_path=str(drainage),
        boundary_conditions={"outfall": "free"},
        infiltration_parameters={"curve": "scs"},
        crs="EPSG:32643",
        grid_shape=(4, 4),
        provenance={"is_observation": True},
    )

    adapter = SWMMAdapter("swmm_dummy")
    # Dry run should build deterministic command when executable is mocked
    adapter.executable_path = lambda: "C:/bin/swmm5.exe"
    dry = adapter.dry_run(scen, tmp_path / "runs")
    assert dry["dry_run"] is True
    assert dry["status"] == ExecutionStatus.READY.value
    assert len(dry["command"]) == 4
    assert dry["command"][0] == "C:/bin/swmm5.exe"


# ---------------------------------------------------------------------------
# 3. PHYSICS DATASET BUILDER & LEAKAGE PREVENTION
# ---------------------------------------------------------------------------


def test_physics_dataset_builder_event_leakage_rejection(tmp_path):
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"dem")
    rough = tmp_path / "rough.tif"
    rough.write_bytes(b"rough")
    rain = tmp_path / "rain.npy"
    rain.write_bytes(b"rain")

    def _make_scen(sid, event):
        return PhysicsScenario(
            scenario_id=sid,
            rainfall_forcing_path=str(rain),
            rainfall_units="mm/h",
            start_time="2024-01-01T00:00:00+00:00",
            end_time="2024-01-01T01:00:00+00:00",
            temporal_resolution_minutes=30,
            dem_path=str(dem),
            roughness_path=str(rough),
            drainage_network_path=None,
            boundary_conditions={"b": 1},
            infiltration_parameters={"i": 1},
            crs="EPSG:32643",
            grid_shape=(4, 4),
            provenance={"rainfall_event": event},
        )

    def _make_res(sid):
        p_depth = tmp_path / f"{sid}_depth.npy"
        p_depth.write_bytes(b"depth")
        return PhysicsResult(
            scenario_id=sid,
            max_depth_path=str(p_depth),
            depth_timeseries_path=str(p_depth),
            inundation_extent_path=str(p_depth),
            velocity_path=None,
            valid_mask_path=str(p_depth),
            solver="LISFLOOD-FP",
            solver_version="8.0",
            runtime_seconds=12.5,
            status="SUCCESS",
            convergence="CONVERGED",
            input_hashes={"dem": "0" * 64},
            output_hashes={"depth": "1" * 64},
            physically_simulated=True,
            calibrated=False,
        )

    builder = PhysicsDatasetBuilder()
    s1 = _make_scen("scen_1", "event_A")
    s2 = _make_scen("scen_2", "event_A")  # perturbation of event_A
    r1 = _make_res("scen_1")
    r2 = _make_res("scen_2")

    builder.add_entry(s1, r1, split="train")
    # Placing s2 in validation causes leakage of event_A!
    builder.add_entry(s2, r2, split="validation")

    with pytest.raises(ValueError, match="Data leakage detected across splits"):
        builder.freeze(tmp_path / "out_dataset.json")


# ---------------------------------------------------------------------------
# 4. FNO FLOOD SURROGATE & EVALUATION METRICS
# ---------------------------------------------------------------------------


def test_fno_architecture_and_sparse_flood_loss():
    model = FloodFNO(input_channels=4, width=8, modes=4, output_horizons=4)
    inputs = torch.randn(2, 4, 16, 16)
    preds = model(inputs)

    # Output shape: [B, 4, 1, H, W]
    assert preds.shape == (2, 4, 1, 16, 16)
    # Non-negative depth guarantee via softplus
    assert torch.all(preds >= 0.0)

    # Test SparseFloodLoss
    loss_fn = SparseFloodLoss(wet_threshold=0.05, wet_weight=4.0)
    target = torch.zeros(2, 4, 1, 16, 16)
    target[:, :, :, 8:12, 8:12] = 0.5  # Sparse flood inundation
    mask = torch.ones_like(target, dtype=torch.bool)

    loss = loss_fn(preds, target, mask)
    assert torch.isfinite(loss)
    assert loss.item() > 0.0


def test_fno_evaluation_metrics():
    pred = np.array([[0.0, 0.10], [0.50, 0.0]], dtype=np.float32)
    ref = np.array([[0.0, 0.08], [0.60, 0.0]], dtype=np.float32)
    mask = np.ones((2, 2), dtype=bool)

    metrics = evaluate_fno(
        pred, ref, mask,
        threshold=0.05,
        runtime_seconds=0.02,
        reference_runtime_seconds=1.20,
    )

    assert metrics["depth_mae_m"] == pytest.approx(0.03, abs=1e-3)
    assert metrics["inundation_iou"] == 1.0  # both detect cells (0,1) and (1,0)
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["measured_speedup"] == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# 5. EXPOSURE & VULNERABILITY
# ---------------------------------------------------------------------------


def test_exposure_engine_normalized_and_raw():
    raw_pop = np.array([[0.0, 500.0], [1000.0, 0.0]], dtype=np.float32)
    layer = ExposureAssetLayer(
        layer_id="pop_layer",
        asset_class=AssetClass.POPULATION,
        geometry_type="raster",
        crs="EPSG:32643",
        source="test_census",
        source_version="v1",
        source_sha256="1" * 64,
        vintage="2024",
        raw_values=raw_pop,
        max_scale_value=1000.0,
    )
    layer.validate()
    norm = layer.normalized_values
    assert norm is not None
    assert norm[1, 0] == 1.0
    assert norm[0, 1] == 0.5

    hazard = np.array([[0.1, 0.8], [0.9, 0.2]], dtype=np.float32)
    engine = AdvancedExposureEngine()
    res = engine.aggregate_raster_intersection(hazard, layer, hazard_threshold=0.5, hazard_crs="EPSG:32643")
    assert res["status"] == "AVAILABLE"
    assert res["exposed_raw_sum"] == 1500.0
    assert res["exposed_cell_count"] == 2
    assert res["exposed_normalized_score"] == pytest.approx(0.75)


def test_vulnerability_insufficient_data_status():
    engine = VulnerabilityEngine(min_required_factors=2)
    # Only 1 factor available
    factors = [
        SourcedVulnerabilityFactor(
            dimension=VulnerabilityDimension.BUILDING,
            value=0.6,
            weight=1.0,
            source="test_survey",
        ),
        SourcedVulnerabilityFactor(
            dimension=VulnerabilityDimension.ACCESSIBILITY,
            value=None,
            weight=1.0,
            source=None,
        ),
    ]

    report = engine.evaluate_vulnerability(factors)
    assert report["status"] == VULNERABILITY_DATA_INSUFFICIENT
    assert report["composite_vulnerability"] is None
    assert report["missing_factors"] == [VulnerabilityDimension.ACCESSIBILITY.value]


# ---------------------------------------------------------------------------
# 6. PROBABILISTIC RISK & UNCERTAINTY PROPAGATION
# ---------------------------------------------------------------------------


def test_probabilistic_spatial_risk_and_categories():
    methodology = RiskMethodology(
        version="v1",
        hazard_scale=(0.0, 1.0),
        exposure_scale=(0.0, 1.0),
        vulnerability_scale=(0.0, 1.0),
        category_boundaries=(0.2, 0.5, 0.8),
    )
    engine = ProbabilisticHEVRiskEngine(methodology)

    h = np.array([[0.1, 0.9]], dtype=np.float32)
    e = np.array([[0.5, 0.9]], dtype=np.float32)
    v = np.array([[0.5, 0.9]], dtype=np.float32)
    mask = np.ones((1, 2), dtype=bool)

    out = engine.compute_spatial_risk(h, e, v, valid_mask=mask, data_quality="GOOD", model_confidence=0.85)

    # Cell 0: 0.1 * 0.5 * 0.5 = 0.025 (< 0.2 -> LOW)
    # Cell 1: 0.9 * 0.9 * 0.9 = 0.729 (>= 0.5, < 0.8 -> HIGH)
    assert out["risk_categories"][0, 0] == RiskCategory.LOW.value
    assert out["risk_categories"][0, 1] == RiskCategory.HIGH.value


def test_uncertainty_propagator_quantiles_and_exceedance():
    s1 = np.full((2, 2), 0.2, dtype=np.float32)
    s2 = np.full((2, 2), 0.5, dtype=np.float32)
    s3 = np.full((2, 2), 0.8, dtype=np.float32)

    field = UncertaintyPropagator.propagate_ensemble([s1, s2, s3], weights=[0.25, 0.50, 0.25])
    field.validate()

    assert field.mean[0, 0] == pytest.approx(0.50)
    assert "p10" in field.quantiles and "p90" in field.quantiles

    exceed = UncertaintyPropagator.compute_exceedance_probability([s1, s2, s3], threshold=0.4, weights=[0.25, 0.50, 0.25])
    assert exceed[0, 0] == pytest.approx(0.75)  # s2 (0.50) + s3 (0.25) = 0.75


# ---------------------------------------------------------------------------
# 7. EXPLAINABILITY & CITIZEN REPORT VERIFICATION
# ---------------------------------------------------------------------------


def test_explainability_engine_and_formatting():
    explanation = ExplainabilityEngine.explain(
        risk_level="HIGH",
        rainfall_value=45.0,
        susceptibility_value=0.75,
        exposure_value=0.60,
        vulnerability_value=0.40,
        uncertainty_info={"status": "MEASURED", "spread_sd": 0.1},
        data_quality_info={"quality": "PASS"},
        limitations=["No hydraulic calibration"],
        model_versions={"nowcast": "v1"},
        source_versions={"radar": "v1"},
    )
    explanation.validate()
    text = format_risk_explanation(explanation)
    assert "high forecast rainfall intensity" in text
    assert "No hydraulic calibration" in text
    assert "These are model contributions, not causal claims." in text


def test_citizen_report_verification_strict_heuristic():
    report = CitizenReport(
        report_id="rep_1",
        timestamp="2024-07-21T12:00:00+00:00",
        latitude=19.01,
        longitude=72.84,
        text_description="Deep waterlogging under Hindmata bridge",
    )
    engine = CitizenReportVerificationEngine()

    # Case 1: High rain + high susceptibility + multiple reports -> VERIFIED
    res = engine.verify_report(report, local_rainfall_rate_mm_h=35.0, local_susceptibility_score=0.8, nearby_reports_count=3)
    assert res.status == VerificationStatus.VERIFIED
    assert res.ml_verification_available is False  # Must be false
    assert res.to_dict()["verified_by_ai"] is False

    # Case 2: Zero rain + zero susceptibility -> CONFLICTING
    res_conflict = engine.verify_report(report, local_rainfall_rate_mm_h=0.0, local_susceptibility_score=0.1, nearby_reports_count=0)
    assert res_conflict.status == VerificationStatus.CONFLICTING

    # Case 3: Missing inputs -> INSUFFICIENT_EVIDENCE
    res_none = engine.verify_report(report, local_rainfall_rate_mm_h=None, local_susceptibility_score=None)
    assert res_none.status == VerificationStatus.INSUFFICIENT_EVIDENCE


# ---------------------------------------------------------------------------
# 8. BENCHMARK HARNESS & SCIENTIFIC CLAIM GATES
# ---------------------------------------------------------------------------


def test_scientific_claim_gates_enforce_boundaries():
    gates = ScientificClaimGates()
    gates.validate_scientific_integrity()

    # Violating gate constraint must raise
    with pytest.raises(PermissionError, match="Locked rainfall test set"):
        ScientificClaimGates(LOCKED_TEST_TOUCHED=True).validate_scientific_integrity()

    with pytest.raises(ValueError, match="Cannot claim simulation executed without physical inputs"):
        ScientificClaimGates(REAL_PHYSICS_SIMULATION_EXECUTED=True, SWMM_INPUTS_AVAILABLE=False).validate_scientific_integrity()


def test_benchmark_manifest_reproducibility(tmp_path):
    c1 = tmp_path / "config.yaml"
    c1.write_bytes(b"config_content")
    d1 = tmp_path / "data.tif"
    d1.write_bytes(b"data_content")

    harness = FinalBenchmarkHarness(git_commit="a7aa17d12345678")
    manifest = harness.generate_reproducibility_manifest(config_paths=[c1], data_paths=[d1])
    manifest.validate()

    out_file = tmp_path / "benchmark_manifest.json"
    payload = manifest.write_atomic(out_file)

    assert out_file.is_file()
    assert payload["locked_test_accessed"] is False
    assert len(payload["manifest_sha256"]) == 64
    assert payload["train_events"] == harness.AUTHORITATIVE_SPLITS["train"]
