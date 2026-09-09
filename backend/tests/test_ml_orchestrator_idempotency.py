import pytest

from app.domains.models.orchestrator import ModelRunOrchestrator
from app.integrations.ml.provider import StubMLProvider


@pytest.mark.asyncio
async def test_ml_orchestrator_idempotent_execution():
    orchestrator = ModelRunOrchestrator(ml_provider=StubMLProvider())
    fixed_time = "2026-09-08T09:30:00Z"

    # First run
    run1 = await orchestrator.trigger_model_run(
        model_type="NOWCAST",
        model_version="unet-v2",
        data_manifest_id="manifest-imd-001",
        issue_time=fixed_time,
    )
    assert run1["status"] == "COMPLETED"
    assert "nowcast_manifest" in run1["outputs"]
    assert not run1.get("_is_duplicate_request")

    # Duplicate run request with identical issue_time, model_version, data_manifest
    run2 = await orchestrator.trigger_model_run(
        model_type="NOWCAST",
        model_version="unet-v2",
        data_manifest_id="manifest-imd-001",
        issue_time=fixed_time,
    )
    assert run2["run_id"] == run1["run_id"]
    assert run2["idempotency_key"] == run1["idempotency_key"]
    assert run2.get("_is_duplicate_request") is True

    # Run with different issue_time should execute new run
    run3 = await orchestrator.trigger_model_run(
        model_type="NOWCAST",
        model_version="unet-v2",
        data_manifest_id="manifest-imd-001",
        issue_time="2026-09-08T09:45:00Z",
    )
    assert run3["run_id"] != run1["run_id"]
    assert not run3.get("_is_duplicate_request")
