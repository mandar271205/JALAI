import uuid
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, ValidationError
from app.core.security import AuthenticatedUser, get_current_user
from app.db.models import ResponderTask
from app.db.session import get_db
from app.domains.audit.service import audit_service
from app.domains.optimization.engine import resource_optimization_engine

router = APIRouter(prefix="/optimization", tags=["Resource Optimization"])


@router.post("/recommend")
async def generate_resource_recommendation(
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Computes optimal emergency response resource allocations using Google OR-Tools.
    Inputs:
    - pumps: list of dewatering pumps with capacities and coordinates
    - teams: list of rescue teams with sizes and coordinates
    - shelters: list of emergency shelters with capacities and occupancy
    - incidents: active incident locations, categories, and severity priorities
    - evacuation_demands: citizen clusters requiring evacuation

    NEVER AUTO-DISPATCH:
    Output is purely a recommendation requiring human review and approval.
    """
    pumps = payload.get("pumps", [])
    teams = payload.get("teams", [])
    shelters = payload.get("shelters", [])
    incidents = payload.get("incidents", [])
    evacuation_demands = payload.get("evacuation_demands", [])

    if not incidents:
        raise ValidationError("At least one incident is required for resource optimization.")

    result = resource_optimization_engine.solve(
        pumps=pumps,
        teams=teams,
        shelters=shelters,
        incidents=incidents,
        evacuation_demands=evacuation_demands,
    )
    result["plan_id"] = str(uuid.uuid4())
    return result


@router.post("/approve-plan", status_code=status.HTTP_200_OK)
async def approve_and_dispatch_plan(
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Converts a reviewed resource recommendation plan into actionable operational tasks.
    STRICT REQUIREMENT:
    Only authorized human operators (DISASTER_MANAGER or SUPER_ADMIN) can approve plans.
    Every approval creates an immutable, cryptographically hashed audit event.
    """
    if current_user.role not in ["DISASTER_MANAGER", "SUPER_ADMIN"]:
        raise ForbiddenError(
            "Only authorized Disaster Managers and Admins can approve resource allocation plans."
        )

    plan_id = payload.get("plan_id") or str(uuid.uuid4())
    approval_notes = payload.get("approval_notes", "Approved by emergency response commander.")
    suggested_plan = payload.get("suggested_allocation_plan", {})
    team_allocations = suggested_plan.get("team_allocations", [])

    # Convert team allocations into responder tasks
    created_tasks = []
    for alloc in team_allocations:
        team_id = alloc.get("team_id")
        incident_id = alloc.get("assigned_incident_id")
        task_id = str(uuid.uuid4())
        task = ResponderTask(
            task_id=task_id,
            incident_id=incident_id,
            responder_id=team_id,
            status="ASSIGNED",
            task_type="RESCUE_DISPATCH",
            version=1,
            instructions=f"Proceed to incident {incident_id}. Evacuate civilians and coordinate dewatering. Notes: {approval_notes}",
        )
        db.add(task)
        created_tasks.append(
            {
                "task_id": task_id,
                "team_id": team_id,
                "incident_id": incident_id,
                "status": "ASSIGNED",
            }
        )

    # Record append-only cryptographic audit event
    audit_event = await audit_service.record_event(
        db=db,
        actor_id=current_user.user_id,
        actor_role=current_user.role,
        action="RESOURCE_PLAN_APPROVAL",
        target_entity="RESOURCE_ALLOCATION_PLAN",
        target_id=plan_id,
        before_state={"status": "RECOMMENDED", "plan_id": plan_id},
        after_state={
            "status": "APPROVED",
            "plan_id": plan_id,
            "tasks_created_count": len(created_tasks),
            "approval_notes": approval_notes,
        },
        supporting_snapshot={
            "suggested_allocation_plan": suggested_plan,
            "approver": current_user.user_id,
        },
        changes={"approval_notes": approval_notes, "tasks_created": len(created_tasks)},
    )
    await db.commit()

    return {
        "status": "APPROVED",
        "plan_id": plan_id,
        "tasks_dispatched": created_tasks,
        "audit_event": {
            "log_id": audit_event["log_id"],
            "action": audit_event["action"],
            "before_hash": audit_event["before_hash"],
            "after_hash": audit_event["after_hash"],
            "trace_id": audit_event["trace_id"],
        },
    }
