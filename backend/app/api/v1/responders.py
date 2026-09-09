from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.core.security import AuthenticatedUser, UserRole, get_current_user, require_roles
from app.domains.audit.service import audit_service
from app.domains.responders.service import responder_service

router = APIRouter(prefix="/responders", tags=["Field Responders"])


@router.get("/tasks")
async def list_responder_tasks(
    responder_id: str | None = Query(None),
    status: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    # Field responders see their own tasks; admins and officers see all
    target_responder = responder_id
    if current_user.role == UserRole.FIELD_RESPONDER:
        target_responder = current_user.user_id
    return responder_service.list_tasks(responder_id=target_responder, status=status)


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_responder_task(
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(
        require_roles([UserRole.MUNICIPAL_OFFICER, UserRole.ADMIN])
    ),
) -> dict[str, Any]:
    return responder_service.create_task(
        incident_id=payload.get("incident_id", "inc-001"),
        responder_id=payload.get("responder_id", "resp-001"),
        task_type=payload.get("task_type", "VERIFY_LOCATION"),
        priority=payload.get("priority", "HIGH"),
        instructions=payload.get("instructions"),
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
    )


@router.post("/tasks/{task_id}/action")
async def apply_task_action(
    task_id: str,
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    action = payload.get("action", "COMPLETE_TASK")
    base_version = int(payload.get("base_version", 1))
    result = responder_service.apply_action(
        task_id=task_id,
        action=action,
        expected_version=base_version,
        actor_id=current_user.user_id,
        evidence_url=payload.get("evidence_url"),
        measured_depth_cm=payload.get("measured_depth_cm"),
        notes=payload.get("notes"),
    )

    # Record append-only cryptographic audit event
    audit_entry = await audit_service.record_event(
        db=None,
        actor_id=current_user.user_id,
        actor_role=current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role),
        action="RESPONDER_STATUS_UPDATE",
        target_entity="RESPONDER_TASK",
        target_id=task_id,
        before_state={"status": "ASSIGNED", "version": base_version, "task_id": task_id},
        after_state={
            "status": result.get("status"),
            "version": result.get("version"),
            "task_id": task_id,
        },
        changes={"action": action, "measured_depth_cm": payload.get("measured_depth_cm")},
    )
    result["audit_event"] = {
        "log_id": audit_entry["log_id"],
        "action": audit_entry["action"],
        "before_hash": audit_entry["before_hash"],
        "after_hash": audit_entry["after_hash"],
    }
    return result
