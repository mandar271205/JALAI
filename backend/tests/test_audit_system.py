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


@pytest.mark.asyncio
async def test_alert_lifecycle_records_audit_trail_queryable_via_api():
    """
    Verifies that alert approval and publication write verifiable audit trail events
    accessible through the audit logs endpoint.
    """
    client = TestClient(app)

    # 1. Draft alert
    draft_res = client.post(
        "/api/v1/alerts/draft",
        json={
            "headline": "Audit Test Flood Alert",
            "description": "Heavy rainfall runoff",
            "severity": "Extreme",
            "urgency": "Immediate",
            "certainty": "Observed",
            "ward_id": "WARD-08-KURLA",
            "area_description": "Kurla West",
        },
        headers={"X-Mock-Role": "ANALYST", "X-Mock-User": "usr-drafter-audit"},
    )
    assert draft_res.status_code == 201
    alert_id = draft_res.json()["alert_id"]

    # 2. Distinct officer approves
    appr_res = client.post(
        f"/api/v1/alerts/{alert_id}/approve",
        headers={"X-Mock-Role": "ALERT_APPROVER", "X-Mock-User": "usr-approver-distinct"},
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["audit_event"]["action"] == "ALERT_APPROVED"

    # 3. Publish alert
    pub_res = client.post(
        f"/api/v1/alerts/{alert_id}/publish",
        headers={"X-Mock-Role": "ALERT_APPROVER", "X-Mock-User": "usr-approver-distinct"},
    )
    assert pub_res.status_code == 200

    # 4. Disaster Manager queries audit trail
    audit_res = client.get(
        "/api/v1/audit/logs?limit=20",
        headers={"X-Mock-Role": "DISASTER_MANAGER"},
    )
    assert audit_res.status_code == 200
    logs = audit_res.json()
    actions = [l["action"] for l in logs]
    assert "ALERT_APPROVED" in actions
    assert "ALERT_PUBLISHED" in actions

    # Verify cryptographic hashes
    approved_entry = next(l for l in logs if l["action"] == "ALERT_APPROVED" and l["target_id"] == alert_id)
    assert approved_entry["actor_id"] == "usr-approver-distinct"
    assert len(approved_entry["before_hash"]) == 64
    assert len(approved_entry["after_hash"]) == 64
