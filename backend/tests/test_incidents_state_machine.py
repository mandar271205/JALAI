import pytest
from httpx import AsyncClient

from app.core.errors import ValidationError
from app.domains.incidents.state_machine import IncidentStatus, validate_transition


def test_incident_state_machine_valid_progression():
    # Valid happy path
    assert validate_transition("DETECTED", "OPEN") == IncidentStatus.OPEN
    assert validate_transition("OPEN", "ACKNOWLEDGED") == IncidentStatus.ACKNOWLEDGED
    assert validate_transition("ACKNOWLEDGED", "MITIGATING") == IncidentStatus.MITIGATING
    assert validate_transition("MITIGATING", "RESOLVED") == IncidentStatus.RESOLVED
    assert validate_transition("RESOLVED", "CLOSED") == IncidentStatus.CLOSED


def test_incident_state_machine_illegal_transition():
    # Closed incident cannot move straight to mitigating
    with pytest.raises(ValidationError):
        validate_transition("CLOSED", "MITIGATING")

    # Detected cannot skip straight to resolved
    with pytest.raises(ValidationError):
        validate_transition("DETECTED", "RESOLVED")


def test_incident_dismissal_requires_mandatory_reason():
    # Missing reason
    with pytest.raises(ValidationError) as exc:
        validate_transition("OPEN", "DISMISSED", reason=None)
    assert "mandatory non-empty reason" in str(exc.value)

    # Empty whitespace reason
    with pytest.raises(ValidationError):
        validate_transition("OPEN", "DISMISSED", reason="   ")

    # Valid dismissal with reason
    assert (
        validate_transition("OPEN", "DISMISSED", reason="Duplicate sensor alert")
        == IncidentStatus.DISMISSED
    )


@pytest.mark.asyncio
async def test_incident_api_lifecycle_and_timeline(client: AsyncClient):
    # 1. Create incident -> DETECTED
    create_res = await client.post(
        "/api/v1/incidents",
        json={
            "title": "Severe drain overflow near station",
            "category": "WATERLOGGING",
            "latitude": 19.065,
            "longitude": 72.880,
            "severity": "HIGH",
            "notes": "Citizen reports 40cm water",
        },
    )
    assert create_res.status_code == 201
    inc_data = create_res.json()
    incident_id = inc_data["incident_id"]
    assert inc_data["status"] == "DETECTED"
    assert len(inc_data["timeline"]) == 1
    assert inc_data["timeline"][0]["new_status"] == "DETECTED"

    # 2. Transition DETECTED -> OPEN
    trans_res = await client.post(
        f"/api/v1/incidents/{incident_id}/transition",
        json={"target_status": "OPEN", "notes": "Officer confirmed on CCTV"},
    )
    assert trans_res.status_code == 200
    assert trans_res.json()["status"] == "OPEN"

    # 3. Transition OPEN -> ACKNOWLEDGED
    ack_res = await client.post(
        f"/api/v1/incidents/{incident_id}/transition",
        json={"target_status": "ACKNOWLEDGED", "notes": "Disaster control room acknowledged"},
    )
    assert ack_res.status_code == 200
    assert ack_res.json()["status"] == "ACKNOWLEDGED"

    # 4. Verify append-only timeline
    get_res = await client.get(f"/api/v1/incidents/{incident_id}")
    assert get_res.status_code == 200
    fetched = get_res.json()
    assert fetched["status"] == "ACKNOWLEDGED"
    assert len(fetched["timeline"]) >= 3
