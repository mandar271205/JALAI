import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedUser, get_current_user
from app.core.security_hardening import enforce_regional_access
from app.db.session import get_db
from app.domains.audit.service import audit_service
from app.domains.incidents.repository import IncidentsRepository
from app.domains.incidents.state_machine import IncidentStatus

router = APIRouter(prefix="/incidents", tags=["Incidents"])

# In-memory fallback repository for incident operations
repo = IncidentsRepository(session=None)
_memory_incidents: dict[str, dict[str, Any]] = {}
_memory_sos: dict[str, dict[str, Any]] = {}


@router.post("/sos", status_code=status.HTTP_201_CREATED)
async def broadcast_sos_distress(
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    lat = float(payload.get("latitude", 19.0728))
    lon = float(payload.get("longitude", 72.8792))
    ward_id = payload.get("ward_id", "Ward L (Kurla West)")
    citizen_name = payload.get("citizen_name", "Ananya Sharma")
    contact_number = payload.get("contact_number", "+91 98201 12345")
    assistance_needs = payload.get("assistance_needs", [])
    battery_level = payload.get("battery_level", 84)
    notes = payload.get("notes", "Critical Flood Distress Beacon Activated")

    incident = await repo.create_incident(
        title=f"SOS DISTRESS: {citizen_name} ({ward_id})",
        category="SOS_DISTRESS",
        latitude=lat,
        longitude=lon,
        severity="FLASH_CRITICAL",
        ward_id=ward_id,
        reporter_id=current_user.user_id,
        initial_notes=f"Citizen Contact: {contact_number} | Battery: {battery_level}% | Assistance: {', '.join(assistance_needs) if assistance_needs else 'None'} | Notes: {notes}",
    )
    incident["status"] = "DISPATCHED"
    _memory_incidents[incident["incident_id"]] = incident

    sos_id = f"SOS-2026-{int(datetime.now(timezone.utc).timestamp()) % 100000:05d}"
    sos_record = {
        "sos_id": sos_id,
        "incident_id": incident["incident_id"],
        "status": "DISPATCHED",
        "priority": "FLASH_CRITICAL",
        "citizen_name": citizen_name,
        "contact_number": contact_number,
        "latitude": lat,
        "longitude": lon,
        "ward_id": ward_id,
        "assistance_needs": assistance_needs,
        "battery_level": battery_level,
        "assigned_unit": "NDRF 5th Battalion (Kurla Flood Quick-Response)",
        "vehicle_callsign": "AMPHIBIOUS-RAFT-04",
        "responder_phone": "1078",
        "disaster_control_phone": "1916",
        "eta_minutes": 8,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notes": notes,
        "message": "Distress beacon locked. Rapid rescue unit dispatched.",
    }
    _memory_sos[sos_id] = sos_record
    return sos_record


@router.get("/sos/{sos_id}")
async def get_sos_distress(sos_id: str) -> dict[str, Any]:
    if sos_id in _memory_sos:
        return _memory_sos[sos_id]
    return {
        "sos_id": sos_id,
        "status": "DISPATCHED",
        "priority": "FLASH_CRITICAL",
        "assigned_unit": "NDRF 5th Battalion (Kurla Flood Quick-Response)",
        "vehicle_callsign": "AMPHIBIOUS-RAFT-04",
        "responder_phone": "1078",
        "disaster_control_phone": "1916",
        "eta_minutes": 6,
        "message": "Rescue unit en route to locked coordinates.",
    }


@router.post("/sos/{sos_id}/cancel")
async def cancel_sos_distress(
    sos_id: str,
    payload: dict[str, Any] | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    reason = payload.get("reason", "Citizen reported safe") if payload else "Citizen reported safe"
    if sos_id in _memory_sos:
        _memory_sos[sos_id]["status"] = "DE_ESCALATED"
        _memory_sos[sos_id]["cancellation_reason"] = reason
        _memory_sos[sos_id]["resolved_at"] = datetime.now(timezone.utc).isoformat()

        inc_id = _memory_sos[sos_id].get("incident_id")
        if inc_id and inc_id in _memory_incidents:
            _memory_incidents[inc_id]["status"] = "RESOLVED"

    return {
        "sos_id": sos_id,
        "status": "DE_ESCALATED",
        "reason": reason,
        "message": "Distress signal de-escalated. Ward marshals notified.",
    }


@router.get("")
async def list_incidents(
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    ward_id: str | None = Query(None),
) -> list[dict[str, Any]]:
    # Merge fixture incidents with in-memory incidents
    base = Path(__file__).resolve().parents[3]
    fixture_file = base / "contracts" / "fixtures" / "demo-event" / "incidents.json"
    if not fixture_file.exists():
        fixture_file = Path(__file__).resolve().parents[4] / "contracts" / "fixtures" / "demo-event" / "incidents.json"
    incidents = []
    if fixture_file.exists():
        with open(fixture_file, "r", encoding="utf-8") as f:
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
    base = Path(__file__).resolve().parents[3]
    fixture_file = base / "contracts" / "fixtures" / "demo-event" / "incidents.json"
    if not fixture_file.exists():
        fixture_file = Path(__file__).resolve().parents[4] / "contracts" / "fixtures" / "demo-event" / "incidents.json"
    if fixture_file.exists():
        with open(fixture_file, "r", encoding="utf-8") as f:
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
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    target_status = payload.get("target_status") or payload.get("to_status")
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
        db=db,
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
