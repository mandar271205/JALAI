import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import OutboxEvent
from app.db.outbox import OutboxManager
from app.integrations.events.bus import InMemoryEventBus


@pytest.mark.asyncio
async def test_outbox_transactional_record_and_relay():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(OutboxEvent.__table__.create)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    event_bus = InMemoryEventBus()

    # 1. Record event in outbox inside transaction
    async with session_maker() as session:
        evt = await OutboxManager.record_event(
            session=session,
            aggregate_type="Incident",
            aggregate_id="inc-outbox-001",
            event_type="incident.created",
            payload={"title": "Flash Flood Detected", "severity": "CRITICAL"},
        )
        await session.commit()
        assert evt.processed is False

    # 2. Relay pending events to event bus
    async with session_maker() as session:
        relayed = await OutboxManager.relay_pending_events(session=session, event_bus=event_bus)
        assert relayed == 1

    # 3. Verify event bus received the event
    published = await event_bus.get_published_events("events.incident")
    assert len(published) == 1
    assert published[0]["payload"]["event_type"] == "incident.created"
    assert published[0]["payload"]["payload"]["severity"] == "CRITICAL"

    await engine.dispose()
