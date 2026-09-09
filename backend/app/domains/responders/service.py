import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.errors import AppException, NotFoundError, ValidationError

VALID_TASK_TYPES = {
    "VERIFY_LOCATION",
    "MEASURE_DEPTH",
    "ROAD_BLOCKED",
    "DRAIN_BLOCKED",
    "SUPPORT_REQUEST",
    "ROAD_REOPENED",
    "COMPLETE_TASK",
}


class ResponderTaskService:
    def __init__(self):
        self._tasks: dict[str, dict[str, Any]] = {}

    def create_task(
        self,
        incident_id: str,
        responder_id: str,
        task_type: str = "VERIFY_LOCATION",
        priority: str = "HIGH",
        instructions: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> dict[str, Any]:
        if task_type not in VALID_TASK_TYPES:
            raise ValidationError(
                f"Invalid task_type '{task_type}'. Must be one of {VALID_TASK_TYPES}"
            )

        task_id = str(uuid.uuid4())
        task_record = {
            "task_id": task_id,
            "incident_id": incident_id,
            "responder_id": responder_id,
            "task_type": task_type,
            "priority": priority,
            "status": "ASSIGNED",
            "version": 1,  # Base version for optimistic locking
            "latitude": latitude,
            "longitude": longitude,
            "evidence_image_url": None,
            "measured_depth_cm": None,
            "instructions": instructions,
            "assigned_at": datetime.now(UTC).isoformat(),
            "completed_at": None,
            "action_history": [],
        }
        self._tasks[task_id] = task_record
        return task_record

    def get_task(self, task_id: str) -> dict[str, Any]:
        if task_id not in self._tasks:
            raise NotFoundError(f"Responder task '{task_id}' not found.")
        return self._tasks[task_id]

    def list_tasks(
        self, responder_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        results = list(self._tasks.values())
        if responder_id:
            results = [t for t in results if t["responder_id"] == responder_id]
        if status:
            results = [t for t in results if t["status"] == status.upper()]
        return results

    def apply_action(
        self,
        task_id: str,
        action: str,
        expected_version: int,
        actor_id: str,
        evidence_url: str | None = None,
        measured_depth_cm: float | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        task = self.get_task(task_id)

        # Optimistic locking check
        if expected_version != task["version"]:
            raise AppException(
                code="VERSION_CONFLICT",
                message=f"Optimistic lock failure: Task version is {task['version']}, but client provided base version {expected_version}.",
                status_code=409,
                details={"current_version": task["version"], "client_version": expected_version},
            )

        if action not in VALID_TASK_TYPES:
            raise ValidationError(f"Invalid responder action '{action}'.")

        now = datetime.now(UTC).isoformat()
        task["version"] += 1  # Increment version on every mutation

        if action == "MEASURE_DEPTH":
            task["measured_depth_cm"] = measured_depth_cm
            task["status"] = "ON_SCENE"
        elif action in ["ROAD_BLOCKED", "DRAIN_BLOCKED"]:
            task["status"] = "ON_SCENE"
        elif action in ["ROAD_REOPENED", "COMPLETE_TASK"]:
            task["status"] = "COMPLETED"
            task["completed_at"] = now
        else:
            task["status"] = "EN_ROUTE"

        if evidence_url:
            task["evidence_image_url"] = evidence_url

        history_entry = {
            "action": action,
            "actor_id": actor_id,
            "version_after": task["version"],
            "timestamp": now,
            "notes": notes,
        }
        task["action_history"].append(history_entry)

        return task


responder_service = ResponderTaskService()
