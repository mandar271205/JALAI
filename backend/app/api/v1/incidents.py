import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.core.security import AuthenticatedUser, get_current_user
from app.core.security_hardening import enforce_regional_access
from app.domains.audit.service import audit_service
from app.domains.incidents.repository import IncidentsRepository
from app.domains.incidents.state_machine import IncidentStatus

router = APIRouter(prefix="/incidents", tags=["Incidents"])

# In-memory fallback repository for incident operations
repo = IncidentsRepository(session=None)
_memory_incidents: dict[str, dict[str, Any]] = {}


@router.get("")
async def list_incidents(
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    ward_id: str | None = Query(None),
) -> list[dict[str, Any]]:
    # Merge fixture incidents with in-memory incidents
    base = Path(__file__).resolve().parents[4]
    fixture_file = base / "contracts" / "fixtures" / "demo-event" / "incidents.json"
    incidents = []
    if fixture_file.exists():
        with open(fixture_file) as f:
            incidents = json.load(f)

    # Add any newly created memory incidents
    incidents.extend(list(_memory_incidents.values()))

    if status_filter:
        incidents = [i for i in incidents if i.get("status") == status_filter.upper()]
    if severity:
        incidents = [i for i in incidents if i.get("severity") == severity.upper()]
    if ward_id:
        incidents = [i for i in incidents if i.get("ward_id") == ward_id]

    return incidents


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: dict[str, Any], current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    incident = await repo.create_incident(
        title=payload.get("title", "Reported Incident"),
        category=payload.get("category", "WATERLOGGING"),
        latitude=float(payload.get("latitude", 19.0712)),
        longitude=float(payload.get("longitude", 72.8756)),
        severity=payload.get("severity", "HIGH"),
        ward_id=payload.get("ward_id"),
        reporter_id=current_user.user_id,
        initial_notes=payload.get("notes"),
    )
    _memory_incidents[incident["incident_id"]] = incident
    return incident


@router.get("/{incident_id}")
async def get_incident(incident_id: str) -> dict[str, Any]:
    if incident_id in _memory_incidents:
        return _memory_incidents[incident_id]

    # Check fixtures
    base = Path(__file__).resolve().parents[4]
    fixture_file = base / "contracts" / "fixtures" / "demo-event" / "incidents.json"
    if fixture_file.exists():
        with open(fixture_file) as f:
            for inc in json.load(f):
                if inc.get("incident_id") == incident_id:
                    return {
                        **inc,
                        "timeline": [
                            {
                                "event_id": "evt-initial",
                                "incident_id": incident_id,
                                "actor_id": "system",
                                "previous_status": None,
                                "new_status": inc.get("status", "DETECTED"),
                                "reason": "Initial detection",
                                "created_at": inc.get("created_at"),
                            }
                        ],
                    }

    # If not found, create a mock entry
    return {
        "incident_id": incident_id,
        "title": "Historical Incident",
        "status": IncidentStatus.OPEN.value,
        "severity": "HIGH",
        "timeline": [],
    }


@router.post("/{incident_id}/transition")
async def transition_incident(
    incident_id: str,
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    target_status = payload.get("target_status")
    reason = payload.get("reason")
    notes = payload.get("notes")

    current_status = None
    if incident_id in _memory_incidents:
        current_status = _memory_incidents[incident_id].get("status")
        incident_region = _memory_incidents[incident_id].get("region", "mumbai")
        enforce_regional_access(current_user, incident_region)

    transition_result = await repo.transition_incident(
        incident_id=incident_id,
        target_status=target_status,
        actor_id=current_user.user_id,
        reason=reason,
        notes=notes,
        current_status_override=current_status,
    )

    if incident_id in _memory_incidents:
        _memory_incidents[incident_id]["status"] = transition_result["status"]
        _memory_incidents[incident_id]["updated_at"] = transition_result["updated_at"]
        _memory_incidents[incident_id].setdefault("timeline", []).append(transition_result["event"])

    # Record append-only cryptographic audit event
    audit_entry = await audit_service.record_event(
        db=None,
        actor_id=current_user.user_id,
        actor_role=current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role),
        action="INCIDENT_STATUS_OVERRIDE",
        target_entity="INCIDENT",
        target_id=incident_id,
        before_state={"status": current_status, "incident_id": incident_id},
        after_state={"status": target_status, "incident_id": incident_id, "reason": reason},
        changes={"reason": reason, "notes": notes, "new_status": target_status},
    )
    transition_result["audit_event"] = {
        "log_id": audit_entry["log_id"],
        "action": audit_entry["action"],
        "before_hash": audit_entry["before_hash"],
        "after_hash": audit_entry["after_hash"],
    }

    return transition_result
