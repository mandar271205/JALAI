import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OutboxEvent
from app.integrations.events.bus import EventBus


class OutboxManager:
    """
    Transactional Outbox Pattern.
    Guarantees at-least-once delivery of critical domain events by saving the event
    in the same database transaction as the entity state change.
    """

    @staticmethod
    async def record_event(
        session: AsyncSession,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> OutboxEvent:
        event = OutboxEvent(
            event_id=str(uuid.uuid4()),
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload_json=payload,
            processed=False,
            created_at=datetime.now(UTC),
        )
        session.add(event)
        return event

    @staticmethod
    async def relay_pending_events(session: AsyncSession, event_bus: EventBus) -> int:
        result = await session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.processed.is_(False))
            .order_by(OutboxEvent.created_at)
        )
        pending = result.scalars().all()
        relayed_count = 0

        for event in pending:
            topic = f"events.{event.aggregate_type.lower()}"
            await event_bus.publish(
                topic,
                {
                    "event_id": event.event_id,
                    "aggregate_id": event.aggregate_id,
                    "event_type": event.event_type,
                    "payload": event.payload_json,
                    "created_at": event.created_at.isoformat(),
                },
            )
            event.processed = True
            relayed_count += 1

        if relayed_count > 0:
            await session.commit()

        return relayed_count
