from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from jalrakshak_ml.citizen.baseline import inspect_training_readiness
from jalrakshak_ml.citizen.dataset import CitizenDatasetBuilder, CitizenLabel, LabeledCitizenSample
from jalrakshak_ml.citizen.verification_v2 import (
    CitizenReportV2,
    CitizenVerificationEngineV2,
    CitizenVerificationState,
)
from jalrakshak_ml.evidence.catalog import EventCatalog, EventState, FloodEvent
from jalrakshak_ml.evidence.contracts import (
    EvidenceRecord,
    EvidenceRegistry,
    EvidenceType,
    QuantityType,
    VerificationState,
)
from jalrakshak_ml.explain.risk_explanation_v2 import explain_risk_v2
from jalrakshak_ml.research.benchmark import (
    BenchmarkMetric,
    MetricStatus,
    assemble_benchmark,
    benchmark_skeleton,
)
from jalrakshak_ml.research.claims import ClaimStatus, evaluate_claim
from jalrakshak_ml.research.confidence import CompositeConfidence
from jalrakshak_ml.research.decision import fallback_matrix
from jalrakshak_ml.research.freshness import FreshnessState, classify_freshness
from jalrakshak_ml.research.integration import run_offline_dryrun
from jalrakshak_ml.research.registry import ArtifactRegistry, Lifecycle, RegistryRecord
from jalrakshak_ml.research.reproducibility import build_reproducibility_bundle
from jalrakshak_ml.research.run_manifest import RunManifest
from jalrakshak_ml.research.serving import ServingState, serialize_internal_response
from jalrakshak_ml.research.sources import default_source_capabilities
from jalrakshak_ml.research.statistics import paired_block_bootstrap
from jalrakshak_ml.research.tables import export_research_table


def evidence(**updates):
    payload = {
        "evidence_id": "ev-1",
        "event_id": "mumbai_monsoon_2025_07_01",
        "start_time": "2025-07-01T00:00:00+00:00",
        "end_time": "2025-07-01T00:30:00+00:00",
        "geometry": None,
        "spatial_reference": "Mumbai pilot grid",
        "source": "derived susceptibility",
        "source_reference": None,
        "source_organization": "JalRakshak",
        "evidence_type": EvidenceType.SUSCEPTIBILITY_ONLY,
        "quantity_type": QuantityType.SUSCEPTIBILITY_SCORE,
        "value": 0.8,
        "units": "dimensionless",
        "crs": "EPSG:4326",
        "spatial_resolution": "canonical grid",
        "temporal_resolution": "event",
        "confidence": None,
        "quality_score": 0.7,
        "verification_state": VerificationState.PARTIAL,
        "provenance": {"config": "phase8_v1"},
        "checksum": "a" * 64,
        "created_at": "2026-09-09T00:00:00+00:00",
        "caveats": ("not depth",),
    }
    payload.update(updates)
    return EvidenceRecord(**payload)


def citizen_sample(
    report_id, event_id, label=CitizenLabel.GENUINE_SUPPORTED, duplicate_group_id=None
):
    return LabeledCitizenSample(
        report_id,
        event_id,
        "2025-07-01T00:00:00+00:00",
        "road flooding",
        {"rain_mm_h": 10.0},
        label,
        "field-review-1",
        {"method": "human_annotation"},
        duplicate_group_id,
    )


def test_evidence_type_safety_and_roundtrip():
    record = evidence()
    assert EvidenceRecord.from_dict(record.to_dict()) == record
    assert record.require_quantity(QuantityType.SUSCEPTIBILITY_SCORE) is record


def test_susceptibility_cannot_be_depth_or_extent():
    with pytest.raises(ValueError, match="cannot be depth"):
        evidence(quantity_type=QuantityType.WATER_DEPTH, units="m").validate()
    with pytest.raises(TypeError):
        evidence().require_quantity(QuantityType.WATER_DEPTH)


def test_unverified_citizen_cannot_be_verified_truth():
    with pytest.raises(ValueError, match="cannot be promoted"):
        evidence(
            evidence_type=EvidenceType.CITIZEN_REPORTED,
            quantity_type=QuantityType.REPORT_LOCATION,
            units="point",
            verification_state=VerificationState.VERIFIED,
        ).validate()


def test_evidence_registry_hash_and_immutability(tmp_path):
    path = tmp_path / "evidence.json"
    payload = EvidenceRegistry([evidence()]).write_atomic(path)
    assert len(payload["registry_sha256"]) == 64
    assert EvidenceRegistry.load(path).records[0].evidence_id == "ev-1"
    with pytest.raises(FileExistsError):
        EvidenceRegistry([evidence()]).write_atomic(path)


def test_event_catalog_candidate_cannot_claim_severity():
    event = FloodEvent(
        "mumbai_monsoon_2025_07_01",
        "2025-07-01T00:00:00+00:00",
        "2025-07-01T12:00:00+00:00",
        EventState.CANDIDATE,
        severity="extreme",
        severity_evidence_refs=("ev",),
    )
    with pytest.raises(ValueError):
        event.validate()


def test_event_catalog_safe_transitions(tmp_path):
    event = FloodEvent(
        "mumbai_monsoon_2025_07_01",
        "2025-07-01T00:00:00+00:00",
        "2025-07-01T12:00:00+00:00",
        EventState.CANDIDATE,
        rainfall_evidence_refs=("rain",),
        flood_evidence_refs=("flood",),
    )
    partial = event.transition(EventState.EVIDENCE_PARTIAL, reason="two evidence classes present")
    verified = partial.transition(EventState.EVIDENCE_VERIFIED, reason="manual evidence audit")
    assert verified.state is EventState.EVIDENCE_VERIFIED
    with pytest.raises(ValueError, match="Unsafe"):
        event.transition(EventState.BENCHMARK_ELIGIBLE, reason="skip")
    path = tmp_path / "events.json"
    assert EventCatalog([verified]).write_atomic(path)["catalog_sha256"]
    assert EventCatalog.load(path).events[0] == verified


def test_benchmark_eligibility_requires_exposure_and_vulnerability():
    event = FloodEvent(
        "mumbai_monsoon_2025_07_01",
        "2025-07-01T00:00:00+00:00",
        "2025-07-01T12:00:00+00:00",
        EventState.BENCHMARK_ELIGIBLE,
        rainfall_evidence_refs=("rain",),
        flood_evidence_refs=("flood",),
    )
    with pytest.raises(ValueError, match="exposure"):
        event.validate()


def report(**updates):
    base = {
        "report_id": "r1",
        "event_id": "mumbai_monsoon_fixture",
        "timestamp": "2025-07-01T01:00:00+00:00",
        "latitude": 19.1,
        "longitude": 72.9,
        "h3_index": "h3",
        "claimed_flood_type": "street",
        "claimed_depth_category": None,
        "text": "water on street",
        "rainfall_context_mm_h": 15.0,
        "corroborating_report_ids": ("r2", "r3"),
    }
    base.update(updates)
    return CitizenReportV2(**base)


def test_citizen_v2_never_returns_verified_truth():
    result = CitizenVerificationEngineV2().verify(report())
    assert result.state is CitizenVerificationState.CORROBORATED
    assert result.verified_flood_truth is False
    assert result.ml_available is False
    assert result.support_score_type.startswith("HEURISTIC")


def test_citizen_spam_rejection():
    result = CitizenVerificationEngineV2().verify(report(duplicate_report_ids=("a", "b", "c")))
    assert result.state is CitizenVerificationState.REJECTED_SPAM


def test_citizen_conflicting_evidence():
    result = CitizenVerificationEngineV2().verify(report(rainfall_context_mm_h=0.0))
    assert result.state is CitizenVerificationState.CONFLICTING_EVIDENCE


def test_dataset_duplicate_leakage_rejected(tmp_path):
    samples = [
        citizen_sample("a", "e1", duplicate_group_id="dup"),
        citizen_sample("b", "e2", duplicate_group_id="dup"),
    ]
    with pytest.raises(ValueError, match="cannot cross"):
        CitizenDatasetBuilder().build(
            samples, {"e1": "train", "e2": "test"}, tmp_path / "manifest.json"
        )


def test_dataset_unknown_excluded_and_hashes(tmp_path):
    sample = citizen_sample("a", "e1", CitizenLabel.UNKNOWN)
    payload = CitizenDatasetBuilder().build([sample], {"e1": "train"}, tmp_path / "manifest.json")
    assert payload["samples"][0]["supervised_eligible"] is False
    assert payload["unknown_used_for_supervised_training"] is False
    assert len(payload["manifest_sha256"]) == 64


def test_dataset_rejects_pseudo_labels(tmp_path):
    sample = LabeledCitizenSample(
        "a",
        "e1",
        "2025-01-01T00:00:00+00:00",
        "x",
        {},
        CitizenLabel.LIKELY_SPAM,
        "model",
        {"method": "pseudo_label"},
    )
    with pytest.raises(ValueError, match="Pseudo-labels"):
        CitizenDatasetBuilder().build([sample], {"e1": "train"}, tmp_path / "manifest.json")


def test_baseline_readiness_false_without_eligible_labels(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"samples": [{"supervised_eligible": False}]}))
    status = inspect_training_readiness(path)
    assert status["CITIZEN_ML_TRAINING_READY"] is False
    assert status["CITIZEN_ML_TRAINING_STARTED"] is False


def test_registry_blocks_unfinished_phase4e_freeze():
    row = RegistryRecord(
        "m",
        "model",
        Lifecycle.FROZEN,
        "v",
        None,
        None,
        "a",
        "1234567",
        None,
        None,
        None,
        {},
        datetime.now(UTC).isoformat(),
        {"phase4e_unfinished": True},
    )
    with pytest.raises(ValueError, match="unfinished"):
        ArtifactRegistry([row])


def test_registry_hash(tmp_path):
    row = RegistryRecord(
        "d",
        "data",
        Lifecycle.DEVELOPMENT,
        None,
        "v",
        None,
        "a",
        "1234567",
        None,
        None,
        None,
        {},
        datetime.now(UTC).isoformat(),
    )
    payload = ArtifactRegistry([row]).write(tmp_path / "registry.json")
    assert len(payload["registry_sha256"]) == 64


def test_claim_gates_block_depth_radar_probability_and_allow_susceptibility():
    assert evaluate_claim("FLOOD_DEPTH", set()).status is ClaimStatus.BLOCKED
    assert (
        evaluate_claim("REALTIME_RADAR_NOWCAST", {"actual_radar_source"}).status
        is ClaimStatus.BLOCKED
    )
    assert evaluate_claim("CALIBRATED_PROBABILITY", set()).status is ClaimStatus.BLOCKED
    assert (
        evaluate_claim("FLOOD_SUSCEPTIBILITY", {"susceptibility_output"}).status
        is ClaimStatus.ALLOWED
    )


def test_not_evaluable_metrics_are_not_zero():
    metric = BenchmarkMetric(
        "fno", "UNAVAILABLE", "target_MAE", MetricStatus.NOT_EVALUABLE, None, None, "no targets"
    )
    assert metric.to_dict()["status"] == "NOT_EVALUABLE"
    with pytest.raises(ValueError):
        BenchmarkMetric(
            "fno", "x", "target_MAE", MetricStatus.NOT_EVALUABLE, 0.0, None, "missing"
        ).validate()
    assert all(row.value is None for row in benchmark_skeleton({}))


def test_benchmark_consumes_only_explicit_evaluated_values():
    evaluated = BenchmarkMetric(
        "rainfall", "future-frozen-model", "MAE", MetricStatus.EVALUATED, 1.2, "mm/h", None, 3
    )
    rows = assemble_benchmark([evaluated])
    assert (
        next(row for row in rows if row.dimension == "rainfall" and row.metric == "MAE")
        == evaluated
    )
    assert next(row for row in rows if row.dimension == "fno").status is MetricStatus.NOT_EVALUABLE


def test_event_block_bootstrap_is_paired_and_reports_blocks():
    result = paired_block_bootstrap(
        [1, 2, 3, 4], [2, 3, 5, 6], n_resamples=200, seed=3, unit="event"
    )
    assert result["independent_blocks"] == 4
    assert result["mean_difference"] == pytest.approx(1.5)
    assert result["unit"] == "event"
    with pytest.raises(ValueError):
        paired_block_bootstrap([1], [1, 2], unit="event")


@pytest.mark.parametrize(
    "age,state",
    [(20, FreshnessState.FRESH), (100, FreshnessState.DEGRADED), (200, FreshnessState.STALE)],
)
def test_freshness_states(age, state):
    result = classify_freshness(
        "x",
        reference_time="2025-01-01T04:00:00+00:00",
        observation_time=f"2025-01-01T{(240 - age) // 60:02d}:{(240 - age) % 60:02d}:00+00:00",
        expected_cadence_minutes=60,
    )
    assert result.state is state


def test_assumed_availability_is_not_observed():
    result = classify_freshness(
        "GFS",
        reference_time="2025-01-01T01:00:00+00:00",
        observation_time="2025-01-01T00:00:00+00:00",
        expected_cadence_minutes=60,
        availability_basis="ASSUMED",
    )
    assert result.availability_basis == "ASSUMED"
    assert any("assumed" in reason for reason in result.reasons)


def test_observed_availability_requires_timestamp():
    with pytest.raises(ValueError, match="requires its timestamp"):
        classify_freshness(
            "GFS",
            reference_time="2025-01-01T01:00:00+00:00",
            observation_time="2025-01-01T00:00:00+00:00",
            expected_cadence_minutes=60,
            availability_basis="OBSERVED",
        )


def test_confidence_components_remain_separate():
    confidence = CompositeConfidence.with_heuristic_summary(
        data_quality=0.9,
        model_confidence=0.2,
        source_coverage=0.5,
        freshness=None,
        uncertainty=0.3,
        physics_validity=0.0,
        exposure_completeness=0.7,
        vulnerability_completeness=0.1,
    )
    assert confidence.data_quality != confidence.model_confidence
    assert confidence.combined_summary_type == "HEURISTIC_NOT_CALIBRATED"


def test_risk_explanation_v2_contains_caveats():
    confidence = CompositeConfidence(None, None, None, None, None, None, None, None)
    payload = explain_risk_v2(
        tier="HIGH",
        score=0.8,
        hazard=0.8,
        exposure=0.7,
        vulnerability=None,
        confidence=confidence,
        missing_evidence=("vulnerability",),
    ).to_dict()
    assert payload["causal_social_claims_made"] is False
    assert "vulnerability" in payload["missing_evidence"]


@pytest.mark.parametrize(
    "available,expected",
    [
        ({"susceptibility": True}, "SUSCEPTIBILITY_ONLY"),
        ({"calibrated_physics": True}, "CALIBRATED_DEPTH"),
    ],
)
def test_physics_fallback(available, expected):
    assert fallback_matrix(available)["flood_output_mode"] == expected


def test_major_fallbacks_are_explicit():
    result = fallback_matrix(
        {"precipitation": True, "nowcast": True, "susceptibility": True, "exposure": True}
    )
    assert result["radar_available"] is False
    assert result["forecast_mode"] == "NOWCAST_ONLY"
    assert result["risk_mode"] == "REDUCED_EVIDENCE_COMPLETENESS"
    assert result["citizen_verification_mode"] == "RULES_ONLY"


def test_atomic_run_manifest_and_locked_test_protection(tmp_path):
    kwargs = {
        "run_id": "r",
        "git_sha": "1234567",
        "config_hashes": {"c": "h"},
        "source_hashes": {},
        "model_hashes": {},
        "normalization_hash": None,
        "data_split": {},
        "started_at": "x",
        "completed_at": "x",
        "machine_device": {},
        "cuda_info": {},
        "random_seeds": {},
        "input_sources": [],
        "output_artifacts": [],
        "evaluation_metrics": [],
        "scientific_claim_gates": [],
    }
    path = tmp_path / "run.json"
    assert RunManifest(**kwargs).write(path)["locked_test_accessed"] is False
    with pytest.raises(FileExistsError):
        RunManifest(**kwargs).write(path)
    with pytest.raises(PermissionError):
        RunManifest(**kwargs, locked_test_accessed=True).validate()


def test_repro_bundle_excludes_raw_large_and_secrets(tmp_path):
    root = tmp_path / "repo"
    (root / "configs").mkdir(parents=True)
    (root / "raw").mkdir()
    (root / "configs" / "a.yaml").write_text("x: 1")
    (root / "raw" / "gpm.json").write_text("raw")
    (root / ".env").write_text("SECRET=x")
    payload = build_reproducibility_bundle(
        destination=tmp_path / "bundle",
        repo_root=root,
        files=["configs/a.yaml", "raw/gpm.json", ".env"],
        git_commit="1234567",
        git_status="clean",
    )
    assert [row["path"] for row in payload["included_files"]] == ["configs/a.yaml"]
    assert payload["raw_data_included"] is False
    assert payload["credentials_included"] is False
    assert len(payload["bundle_sha256"]) == 64


def test_serving_serialization_blocks_unvalidated_depth():
    with pytest.raises(ValueError, match="Water depth"):
        serialize_internal_response(
            "/internal/v1/inundation", state=ServingState.UNVALIDATED, payload={"water_depth": [1]}
        )
    assert (
        serialize_internal_response(
            "/internal/v1/inundation",
            state=ServingState.EXPERIMENTAL,
            payload={"susceptibility": [0.8]},
        )["state"]
        == "EXPERIMENTAL"
    )


def test_nowcast_serving_contract_preserves_units_and_crs():
    result = serialize_internal_response(
        "/internal/v1/nowcast",
        state=ServingState.FROZEN,
        payload={"rainfall": [], "units": "mm/h", "crs": "EPSG:4326"},
    )
    assert result["data"]["units"] == "mm/h"
    with pytest.raises(ValueError, match="units"):
        serialize_internal_response(
            "/internal/v1/nowcast",
            state=ServingState.FROZEN,
            payload={"rainfall": [], "units": "mm", "crs": "EPSG:4326"},
        )


def test_source_capability_distinguishes_adapter_and_data():
    sources = {source.source_id: source for source in default_source_capabilities()}
    assert sources["IMD_DWR"].actually_integrated is False
    assert sources["IMD_DWR"].actually_populated is False
    assert "not radar" in sources["GPM_FINAL"].scientific_role


def test_offline_dryrun_has_no_fake_physics_or_fno_targets(tmp_path):
    payload = run_offline_dryrun(tmp_path / "run.json", git_sha="1234567")
    assert payload["locked_test_accessed"] is False
    assert payload["output_artifacts"] == [
        {"type": "susceptibility", "semantics": "SUSCEPTIBILITY_ONLY"}
    ]
    fno = [row for row in payload["evaluation_metrics"] if row["dimension"] == "fno"]
    assert fno and all(row["status"] == "NOT_EVALUABLE" for row in fno)


def test_table_export_preserves_missing(tmp_path):
    path = export_research_table(
        "fno_benchmark", [{"metric": "MAE", "value": None}], tmp_path / "table.json"
    )
    assert json.loads(path.read_text())["rows"][0]["value"] == "NA"


def test_phase8_configs_parse_and_disallow_locked_test():
    root = Path(__file__).parents[1]
    for relative in (
        "configs/evidence/phase8_v1.yaml",
        "configs/benchmark/final_benchmark_v1.yaml",
        "configs/citizen/verification_v2.yaml",
        "configs/reproducibility/final_bundle_v1.yaml",
    ):
        assert yaml.safe_load((root / relative).read_text())
    assert (
        yaml.safe_load((root / "configs/benchmark/final_benchmark_v1.yaml").read_text())[
            "locked_test_access_allowed"
        ]
        is False
    )


@pytest.mark.parametrize(
    "script",
    [
        "audit_evidence_registry.py",
        "build_flood_event_catalog.py",
        "build_citizen_dataset.py",
        "train_citizen_baseline.py",
        "check_scientific_claims.py",
        "audit_source_capabilities.py",
        "audit_data_freshness.py",
        "run_final_benchmark.py",
        "build_reproducibility_bundle.py",
        "run_offline_integration_dryrun.py",
        "export_research_tables.py",
        "generate_final_project_status.py",
    ],
)
def test_all_phase8_clis_have_help(script):
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / script), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
