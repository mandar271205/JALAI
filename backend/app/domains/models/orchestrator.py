import hashlib
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from app.integrations.ml.provider import get_ml_provider
from app.realtime.connection_manager import live_manager


class ModelRunOrchestrator:
    def __init__(self, ml_provider=None):
        self.ml_provider = ml_provider or get_ml_provider()
        self._runs_by_idempotency_key: dict[str, dict[str, Any]] = {}
        self._runs_by_id: dict[str, dict[str, Any]] = {}

    def generate_idempotency_key(
        self, issue_time: str, model_version: str, data_manifest_id: str
    ) -> str:
        raw = f"{issue_time}::{model_version}::{data_manifest_id}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def trigger_model_run(
        self,
        model_type: str,
        model_version: str,
        data_manifest_id: str,
        issue_time: str | None = None,
    ) -> dict[str, Any]:
        issue_time = issue_time or datetime.now(UTC).isoformat()
        idempotency_key = self.generate_idempotency_key(issue_time, model_version, data_manifest_id)

        # Idempotency check: if this run was already executed, return cached output without re-running!
        if idempotency_key in self._runs_by_idempotency_key:
            existing = self._runs_by_idempotency_key[idempotency_key]
            return {
                **existing,
                "_is_duplicate_request": True,
                "note": "Returned idempotent cached result; no redundant compute executed",
            }

        start_time = time.time()
        run_id = str(uuid.uuid4())
        run_record = {
            "run_id": run_id,
            "idempotency_key": idempotency_key,
            "model_type": model_type,
            "model_version": model_version,
            "data_manifest_id": data_manifest_id,
            "status": "RUNNING",
            "started_at": datetime.now(UTC).isoformat(),
            "completed_at": None,
            "execution_time_ms": None,
            "outputs": {},
        }
        self._runs_by_id[run_id] = run_record

        # Call ML Provider
        if model_type == "NOWCAST":
            manifest = await self.ml_provider.get_nowcast_manifest()
            run_record["outputs"]["nowcast_manifest"] = manifest
        elif model_type == "INUNDATION":
            manifest = await self.ml_provider.get_inundation_manifest()
            run_record["outputs"]["inundation_manifest"] = manifest
        elif model_type == "RISK_AGGREGATION":
            cells = await self.ml_provider.get_risk_cells()
            run_record["outputs"]["materialized_risk_cells_count"] = len(cells)
            run_record["outputs"]["risk_cells"] = cells

        execution_time_ms = int((time.time() - start_time) * 1000)
        run_record["status"] = "COMPLETED"
        run_record["completed_at"] = datetime.now(UTC).isoformat()
        run_record["execution_time_ms"] = execution_time_ms

        # Cache by idempotency key
        self._runs_by_idempotency_key[idempotency_key] = run_record

        # Emit domain events
        await live_manager.broadcast(
            "model.run.completed",
            {
                "run_id": run_id,
                "model_type": model_type,
                "model_version": model_version,
                "execution_time_ms": execution_time_ms,
            },
        )

        if model_type == "RISK_AGGREGATION":
            await live_manager.broadcast(
                "risk.cell.updated",
                {"run_id": run_id, "cell_count": len(run_record["outputs"].get("risk_cells", []))},
            )

        return run_record


orchestrator = ModelRunOrchestrator()
