import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.core.security import AuthenticatedUser, UserRole, require_roles
from app.db.session import get_db
from app.domains.audit.service import audit_service
from app.integrations.cap.serializer import CAPSerializer
from app.integrations.notifications.provider import get_notification_provider
from app.realtime.connection_manager import live_manager

router = APIRouter(prefix="/alerts", tags=["Alerts"])

# In-memory storage for alert lifecycle management
_alerts_db: dict[str, dict[str, Any]] = {}


@router.post("/draft", status_code=status.HTTP_201_CREATED)
async def draft_alert(
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(
        require_roles([UserRole.ANALYST, UserRole.ALERT_APPROVER, UserRole.ADMIN])
    ),
) -> dict[str, Any]:
    """
    Step 1: AI recommendation or Analyst draft creation.
    Validates required fields: headline, severity, urgency, certainty, area_description.
    """
    severity = payload.get("severity")
    valid_severities = ["Extreme", "Severe", "Moderate", "Minor", "Unknown"]
    if severity not in valid_severities:
        raise ValidationError(f"Invalid severity '{severity}'. Must be one of: {valid_severities}")

    confidence = payload.get("confidence", 0.90)
    if confidence < 0.5:
        raise ValidationError("Alert confidence too low (< 0.50) to submit draft alert.")

    alert_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    alert_data = {
        "alert_id": alert_id,
        "status": "DRAFT",
        "headline": payload.get("headline", "Flash Flood Warning"),
        "description": payload.get("description", ""),
        "instruction": payload.get("instruction", "Move to higher ground immediately."),
        "severity": severity,
        "urgency": payload.get("urgency", "Immediate"),
        "certainty": payload.get("certainty", "Observed"),
        "area_description": payload.get("area_description", "Mumbai Municipal Area"),
        "ward_id": payload.get("ward_id"),
        "source_risk_snapshot": payload.get("source_risk_snapshot", {"max_water_depth_m": 0.85}),
        "confidence": confidence,
        "created_by": current_user.user_id,
        "created_at": now,
        "approved_by": None,
        "approved_at": None,
        "sent_at": None,
        "cap_xml": None,
    }
    _alerts_db[alert_id] = alert_data
    return alert_data


@router.post("/{alert_id}/approve")
async def approve_alert(
    alert_id: str,
    payload: dict[str, Any] | None = None,
    current_user: AuthenticatedUser = Depends(
        require_roles([UserRole.ALERT_APPROVER, UserRole.ADMIN])
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Step 2: Designated Alert Approver validates region, content and authorizes publication.
    """
    if alert_id not in _alerts_db:
        raise NotFoundError(f"Alert '{alert_id}' not found.")

    alert = _alerts_db[alert_id]
    if alert["status"] != "DRAFT":
        raise ValidationError(
            f"Cannot approve alert in status '{alert['status']}'. Must be 'DRAFT'."
        )

    # Regional authorization check: approver must have matching jurisdiction or be ADMIN
    approver_region = current_user.metadata.get("region") or current_user.metadata.get("ward_id")
    alert_region = alert.get("ward_id")
    if (
        current_user.role != UserRole.ADMIN
        and approver_region
        and alert_region
        and approver_region != alert_region
    ):
        raise ForbiddenError(
            f"Approver jurisdiction '{approver_region}' does not match alert region '{alert_region}'."
        )

    # Two-Person Governance Rule: Approver must be a distinct actor from the alert drafter
    if alert.get("created_by") and current_user.user_id == alert.get("created_by"):
        raise ForbiddenError(
            "Two-person authorization violation: The alert creator cannot approve their own alert. "
            "A distinct authorized officer must review and approve."
        )

    now = datetime.now(UTC).isoformat()
    before_state = {"status": alert["status"], "approved_by": alert.get("approved_by")}
    alert["status"] = "APPROVED"
    alert["approved_by"] = current_user.user_id
    alert["approved_at"] = now
    after_state = {"status": alert["status"], "approved_by": alert["approved_by"]}

    audit_entry = await audit_service.record_event(
        db=db,
        actor_id=current_user.user_id,
        actor_role=current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role),
        action="ALERT_APPROVED",
        target_entity="ALERT",
        target_id=alert_id,
        before_state=before_state,
        after_state=after_state,
        supporting_snapshot={"reason": "Two-person authorized regional validation passed"},
    )
    alert["audit_event"] = {
        "log_id": audit_entry["log_id"],
        "action": audit_entry["action"],
    }
    return alert


@router.post("/{alert_id}/publish")
async def publish_alert(
    alert_id: str,
    current_user: AuthenticatedUser = Depends(
        require_roles([UserRole.ALERT_APPROVER, UserRole.MUNICIPAL_OFFICER, UserRole.ADMIN])
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Step 3: Disseminate alert, generate OASIS CAP 1.2 XML, fan out notifications and emit real-time event.
    """
    if alert_id not in _alerts_db:
        raise NotFoundError(f"Alert '{alert_id}' not found.")

    alert = _alerts_db[alert_id]
    if alert["status"] not in ["APPROVED", "DRAFT"]:
        raise ValidationError(f"Cannot publish alert in status '{alert['status']}'.")

    now = datetime.now(UTC).isoformat()
    alert["status"] = "PUBLISHED"
    alert["sent_at"] = now

    # Generate standard OASIS CAP 1.2 XML
    cap_xml = CAPSerializer.to_xml(alert)
    alert["cap_xml"] = cap_xml

    # Fan out to notifications provider
    notifier = get_notification_provider()
    await notifier.send_alert(["broadcast_channel_all"], alert)

    # Broadcast real-time WebSocket event
    await live_manager.broadcast(
        "alert.published",
        {
            "alert_id": alert_id,
            "headline": alert["headline"],
            "severity": alert["severity"],
            "area": alert["area_description"],
            "sent_at": now,
        },
    )

    # Record append-only cryptographic audit event
    audit_entry = await audit_service.record_event(
        db=db,
        actor_id=current_user.user_id,
        actor_role=current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role),
        action="ALERT_PUBLISHED",
        target_entity="ALERT",
        target_id=alert_id,
        before_state={"status": "APPROVED", "alert_id": alert_id},
        after_state={"status": "PUBLISHED", "alert_id": alert_id, "cap_xml": cap_xml},
        supporting_snapshot=alert.get("source_risk_snapshot"),
    )

    return {
        "alert_id": alert_id,
        "status": "PUBLISHED",
        "sent_at": now,
        "cap_xml_preview": cap_xml[:120] + "...",
        "audit_event": {
            "log_id": audit_entry["log_id"],
            "action": audit_entry["action"],
            "before_hash": audit_entry["before_hash"],
            "after_hash": audit_entry["after_hash"],
        },
    }


@router.get("/{alert_id}/cap.xml")
async def get_alert_cap_xml(alert_id: str) -> Response:
    if alert_id not in _alerts_db:
        raise NotFoundError(f"Alert '{alert_id}' not found.")

    alert = _alerts_db[alert_id]
    xml_content = alert.get("cap_xml") or CAPSerializer.to_xml(alert)
    return Response(content=xml_content, media_type="application/xml")
