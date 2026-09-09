import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from app.db.models import AuditLog, OutboxEvent
from app.db.session import get_db
from app.domains.audit.service import audit_service, compute_cryptographic_hash
from app.main import app


def test_cryptographic_hash_computation_and_tamper_evidence():
    state1 = {"status": "OPEN", "priority": "HIGH", "assigned_to": "TEAM-1"}
    state2 = {"status": "OPEN", "priority": "HIGH", "assigned_to": "TEAM-1"}
    state_mutated = {"status": "OPEN", "priority": "CRITICAL", "assigned_to": "TEAM-1"}

    hash1 = compute_cryptographic_hash(state1)
    hash2 = compute_cryptographic_hash(state2)
    hash_mut = compute_cryptographic_hash(state_mutated)

    # Determinism
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex string

    # Tamper evidence
    assert hash1 != hash_mut


@pytest.mark.asyncio
async def test_audit_event_recording_in_database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(AuditLog.__table__.create)
        await conn.run_sync(OutboxEvent.__table__.create)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        # Record event
        evt = await audit_service.record_event(
            db=session,
            actor_id="usr-officer-01",
            actor_role="MUNICIPAL_OFFICER",
            action="INCIDENT_STATUS_OVERRIDE",
            target_entity="INCIDENT",
            target_id="inc-777",
            before_state={"status": "OPEN"},
            after_state={"status": "MITIGATING"},
            trace_id="tr-abc-123",
            supporting_snapshot={"water_depth_cm": 45},
            changes={"status": "MITIGATING"},
        )
        await session.commit()

        assert evt["action"] == "INCIDENT_STATUS_OVERRIDE"
        assert evt["before_hash"] != evt["after_hash"]
        assert evt["trace_id"] == "tr-abc-123"

        # Query back
        logs = await audit_service.list_audit_logs(
            db=session,
            action="INCIDENT_STATUS_OVERRIDE",
            trace_id="tr-abc-123",
        )
        assert len(logs) == 1
        assert logs[0]["actor_id"] == "usr-officer-01"
        assert logs[0]["target_id"] == "inc-777"
        assert logs[0]["before_hash"] == evt["before_hash"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_audit_logs_api_authorization_and_listing():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(AuditLog.__table__.create)
        await conn.run_sync(OutboxEvent.__table__.create)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    # Seed an audit record
    async with session_maker() as session:
        await audit_service.record_event(
            db=session,
            actor_id="usr-approver-09",
            actor_role="ALERT_APPROVER",
            action="ALERT_PUBLISHED",
            target_entity="ALERT",
            target_id="alt-p4-001",
            before_state={"status": "APPROVED"},
            after_state={"status": "PUBLISHED"},
        )
        await session.commit()

    async def override_get_db():
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db

    try:
        client = TestClient(app)

        # 1. Citizen is denied access (403)
        r = client.get("/api/v1/audit/logs", headers={"X-Mock-Role": "CITIZEN"})
        assert r.status_code == 403

        # 2. Field responder is denied access (403)
        r = client.get("/api/v1/audit/logs", headers={"X-Mock-Role": "FIELD_RESPONDER"})
        assert r.status_code == 403

        # 3. Disaster Manager is authorized (200)
        r = client.get("/api/v1/audit/logs", headers={"X-Mock-Role": "DISASTER_MANAGER"})
        assert r.status_code == 200
        logs = r.json()
        assert len(logs) >= 1
        assert logs[0]["action"] == "ALERT_PUBLISHED"
        assert "before_hash" in logs[0]
        assert "after_hash" in logs[0]
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
