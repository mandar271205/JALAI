import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import Incident, IncidentEvent
from app.domains.incidents.state_machine import IncidentStatus, validate_transition


class IncidentsRepository:
    def __init__(self, session: AsyncSession | None = None):
        self.session = session

    async def create_incident(
        self,
        title: str,
        category: str,
        latitude: float,
        longitude: float,
        severity: str = "HIGH",
        ward_id: str | None = None,
        reporter_id: str | None = None,
        initial_notes: str | None = None,
    ) -> dict[str, Any]:
        incident_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        incident_data = {
            "incident_id": incident_id,
            "title": title,
            "severity": severity,
            "status": IncidentStatus.DETECTED.value,
            "category": category,
            "latitude": latitude,
            "longitude": longitude,
            "ward_id": ward_id,
            "reporter_id": reporter_id,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        first_event = {
            "event_id": str(uuid.uuid4()),
            "incident_id": incident_id,
            "actor_id": reporter_id or "system",
            "previous_status": None,
            "new_status": IncidentStatus.DETECTED.value,
            "reason": "Incident detected and logged",
            "notes": initial_notes,
            "created_at": now.isoformat(),
        }

        if self.session:
            db_incident = Incident(
                incident_id=incident_id,
                title=title,
                severity=severity,
                status=IncidentStatus.DETECTED.value,
                category=category,
                latitude=latitude,
                longitude=longitude,
                ward_id=ward_id,
                reporter_id=reporter_id,
                created_at=now,
                updated_at=now,
            )
            db_event = IncidentEvent(
                event_id=first_event["event_id"],
                incident_id=incident_id,
                actor_id=reporter_id or "system",
                previous_status=None,
                new_status=IncidentStatus.DETECTED.value,
                reason="Incident detected and logged",
                notes=initial_notes,
                created_at=now,
            )
            self.session.add(db_incident)
            self.session.add(db_event)
            await self.session.commit()

        return {**incident_data, "timeline": [first_event]}

    async def transition_incident(
        self,
        incident_id: str,
        target_status: str,
        actor_id: str,
        reason: str | None = None,
        notes: str | None = None,
        current_status_override: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        current_status = current_status_override or IncidentStatus.DETECTED.value

        if self.session:
            result = await self.session.execute(
                select(Incident).where(Incident.incident_id == incident_id)
            )
            db_incident = result.scalar_one_or_none()
            if not db_incident:
                raise NotFoundError(f"Incident '{incident_id}' not found.")
            current_status = db_incident.status

        # Validate transition via state machine rules
        validated_status = validate_transition(current_status, target_status, reason=reason)

        event_data = {
            "event_id": str(uuid.uuid4()),
            "incident_id": incident_id,
            "actor_id": actor_id,
            "previous_status": current_status,
            "new_status": validated_status.value,
            "reason": reason,
            "notes": notes,
            "created_at": now.isoformat(),
        }

        if self.session:
            db_incident.status = validated_status.value
            db_incident.updated_at = now
            db_event = IncidentEvent(
                event_id=event_data["event_id"],
                incident_id=incident_id,
                actor_id=actor_id,
                previous_status=current_status,
                new_status=validated_status.value,
                reason=reason,
                notes=notes,
                created_at=now,
            )
            self.session.add(db_event)
            await self.session.commit()

        return {
            "incident_id": incident_id,
            "previous_status": current_status,
            "status": validated_status.value,
            "updated_at": now.isoformat(),
            "event": event_data,
        }
