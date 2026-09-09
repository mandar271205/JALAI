import pytest
from starlette.testclient import TestClient

from app.domains.optimization.engine import resource_optimization_engine
from app.main import app


def test_or_tools_optimization_solver():
    pumps = [
        {
            "pump_id": "P-01",
            "name": "500 LPS Submersible",
            "capacity_lps": 500,
            "latitude": 19.018,
            "longitude": 72.848,
        },
        {
            "pump_id": "P-02",
            "name": "300 LPS High Head",
            "capacity_lps": 300,
            "latitude": 19.070,
            "longitude": 72.880,
        },
    ]
    teams = [
        {
            "team_id": "T-01",
            "name": "NDRF Unit 1",
            "team_size": 10,
            "latitude": 19.020,
            "longitude": 72.850,
        },
        {
            "team_id": "T-02",
            "name": "SDRF Unit 2",
            "team_size": 8,
            "latitude": 19.065,
            "longitude": 72.875,
        },
    ]
    shelters = [
        {
            "shelter_id": "S-01",
            "name": "Dharavi Community Center",
            "capacity": 200,
            "current_occupancy": 50,
            "latitude": 19.040,
            "longitude": 72.860,
        },
        {
            "shelter_id": "S-02",
            "name": "Kurla Relief School",
            "capacity": 150,
            "current_occupancy": 100,
            "latitude": 19.068,
            "longitude": 72.885,
        },
    ]
    incidents = [
        {
            "incident_id": "inc-01",
            "title": "Hindmata Underpass Flooding",
            "category": "WATERLOGGING",
            "severity": "CRITICAL",
            "latitude": 19.0178,
            "longitude": 72.8478,
            "zone_risk_score": 0.85,
        },
        {
            "incident_id": "inc-02",
            "title": "Kurla West Waterlogging",
            "category": "WATERLOGGING",
            "severity": "HIGH",
            "latitude": 19.0700,
            "longitude": 72.8800,
            "zone_risk_score": 0.70,
        },
    ]
    demands = [
        {
            "demand_id": "D-01",
            "location_name": "Mithi River Slums",
            "people_count": 80,
            "latitude": 19.066,
            "longitude": 72.870,
        }
    ]

    result = resource_optimization_engine.solve(
        pumps=pumps,
        teams=teams,
        shelters=shelters,
        incidents=incidents,
        evacuation_demands=demands,
    )

    assert result["status"] in ["OPTIMAL", "FEASIBLE"]
    assert result["objective_score"] > 0
    assert result["policy_rules"]["auto_dispatch"] is False
    assert result["policy_rules"]["human_approval_required"] is True

    plan = result["suggested_allocation_plan"]
    assert len(plan["pump_allocations"]) == 2
    assert len(plan["team_allocations"]) == 2
    assert len(plan["shelter_allocations"]) >= 1


def test_recommendation_api_endpoint():
    client = TestClient(app)

    payload = {
        "pumps": [
            {"pump_id": "P-01", "capacity_lps": 500, "latitude": 19.018, "longitude": 72.848}
        ],
        "teams": [{"team_id": "T-01", "team_size": 6, "latitude": 19.020, "longitude": 72.850}],
        "shelters": [
            {
                "shelter_id": "S-01",
                "capacity": 200,
                "current_occupancy": 10,
                "latitude": 19.040,
                "longitude": 72.860,
            }
        ],
        "incidents": [
            {
                "incident_id": "inc-test-01",
                "title": "Submerged Junction",
                "severity": "CRITICAL",
                "category": "WATERLOGGING",
                "latitude": 19.019,
                "longitude": 72.849,
            }
        ],
    }

    r = client.post(
        "/api/v1/optimization/recommend", json=payload, headers={"X-Mock-Role": "DISASTER_MANAGER"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "OPTIMAL"
    assert "plan_id" in data
    assert data["policy_rules"]["auto_dispatch"] is False


def test_unauthorized_role_cannot_approve_plan():
    client = TestClient(app)
    payload = {
        "plan_id": "plan-123",
        "approval_notes": "Attempt by citizen",
        "suggested_allocation_plan": {},
    }
    # CITIZEN role must be forbidden
    r = client.post(
        "/api/v1/optimization/approve-plan", json=payload, headers={"X-Mock-Role": "CITIZEN"}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_authorized_plan_approval_creates_audit_event():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.db.models import AuditLog, OutboxEvent, ResponderTask
    from app.db.session import get_db

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(ResponderTask.__table__.create)
        await conn.run_sync(AuditLog.__table__.create)
        await conn.run_sync(OutboxEvent.__table__.create)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db

    try:
        client = TestClient(app)
        payload = {
            "plan_id": "plan-xyz-999",
            "approval_notes": "Commander approval for monsoon storm deployment",
            "suggested_allocation_plan": {
                "team_allocations": [
                    {"team_id": "TEAM-ALPHA", "assigned_incident_id": "INC-P4-001"}
                ]
            },
        }

        r = client.post(
            "/api/v1/optimization/approve-plan",
            json=payload,
            headers={"X-Mock-Role": "DISASTER_MANAGER", "X-Mock-User": "usr-mgr-777"},
        )
        assert r.status_code == 200
        resp = r.json()
        assert resp["status"] == "APPROVED"
        assert "audit_event" in resp
        audit = resp["audit_event"]
        assert audit["action"] == "RESOURCE_PLAN_APPROVAL"
        assert audit["before_hash"] is not None
        assert audit["after_hash"] is not None
        assert audit["before_hash"] != audit["after_hash"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
