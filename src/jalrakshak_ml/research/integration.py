"""Offline Phase 8 integration dry run using explicit non-truth fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jalrakshak_ml.citizen.verification_v2 import CitizenReportV2, CitizenVerificationEngineV2

from .benchmark import benchmark_skeleton
from .claims import evaluate_all
from .common import canonical_hash
from .confidence import CompositeConfidence
from .decision import AdvisoryAction, DecisionSupport, fallback_matrix
from .run_manifest import RunManifest, cuda_metadata, local_machine_metadata
from .sources import default_source_capabilities


def run_offline_dryrun(output_manifest: str | Path, *, git_sha: str = "0000000") -> dict[str, Any]:
    """Exercise contracts without loading locked tests or inventing depth/physics truth."""
    availability = {
        "radar": False,
        "precipitation": True,
        "fresh_gfs": False,
        "nowcast": True,
        "calibrated_physics": False,
        "susceptibility": True,
        "exposure": True,
        "vulnerability": False,
        "citizen_ml": False,
    }
    fallback = fallback_matrix(availability)
    confidence = CompositeConfidence.with_heuristic_summary(
        data_quality=0.8,
        model_confidence=None,
        source_coverage=0.5,
        freshness=0.6,
        uncertainty=0.6,
        physics_validity=0.0,
        exposure_completeness=0.7,
        vulnerability_completeness=0.0,
    )
    report = CitizenReportV2(
        "fixture-report",
        "mumbai_monsoon_fixture",
        "2026-01-01T00:00:00+00:00",
        19.07,
        72.87,
        None,
        "street_flooding",
        None,
        "water reported on road",
        rainfall_context_mm_h=12.0,
        corroborating_report_ids=("fixture-neighbor",),
    )
    citizen = CitizenVerificationEngineV2().verify(report)
    claims = evaluate_all({"susceptibility_output"})
    metrics = [
        metric.to_dict()
        for metric in benchmark_skeleton({"flood_physics": "UNAVAILABLE", "fno": "UNAVAILABLE"})
    ]
    now = datetime.now(UTC).isoformat()
    config_payload = {"mode": "offline_fixture", "locked_test": False, "water_depth": False}
    manifest = RunManifest(
        run_id=f"phase8-dryrun-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        git_sha=git_sha,
        config_hashes={"dryrun": canonical_hash(config_payload)},
        source_hashes={},
        model_hashes={},
        normalization_hash=None,
        data_split={"fixture_only": True},
        started_at=now,
        completed_at=now,
        machine_device=local_machine_metadata(),
        cuda_info=cuda_metadata(),
        random_seeds={"python": 42, "numpy": 42},
        input_sources=[source.to_dict() for source in default_source_capabilities()],
        output_artifacts=[{"type": "susceptibility", "semantics": "SUSCEPTIBILITY_ONLY"}],
        evaluation_metrics=metrics,
        scientific_claim_gates=[claim.to_dict() for claim in claims],
        locked_test_accessed=False,
    )
    written = manifest.write(output_manifest)
    decision = DecisionSupport(
        AdvisoryAction.VERIFY_LOCALLY,
        "Susceptibility and citizen context warrant local review; calibrated depth is unavailable.",
        ("susceptibility fixture", "rules-only citizen corroboration"),
        confidence.to_dict(),
        ("no calibrated physics", "vulnerability evidence missing"),
        ("human confirmation required",),
    )
    return {
        "locked_test_accessed": False,
        "source_registry_count": len(default_source_capabilities()),
        "forecast_contract": {"state": "EXPERIMENTAL", "units": "mm/h", "crs": "EPSG:4326"},
        "flood_output_mode": "SUSCEPTIBILITY_ONLY",
        "output_artifacts": written["output_artifacts"],
        "evaluation_metrics": written["evaluation_metrics"],
        "real_water_depth_used": False,
        "fabricated_depth_used": False,
        "citizen_verification": citizen.to_dict(),
        "fallback": fallback,
        "recommendation": decision.to_dict(),
        "benchmark_metrics": metrics,
        "run_manifest": written,
    }
