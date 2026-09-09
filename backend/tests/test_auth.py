import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_rbac_allow_authorized_role(client: AsyncClient):
    # Alert drafting requires ANALYST, ALERT_APPROVER, or ADMIN
    headers = {"X-Mock-Role": "ALERT_APPROVER", "X-Mock-User": "usr-approver-001"}
    response = await client.post(
        "/api/v1/alerts/draft",
        json={"headline": "Severe Cyclone Alert", "severity": "Extreme"},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_auth_rbac_forbidden_for_unauthorized_role(client: AsyncClient):
    # CITIZEN role cannot draft emergency alerts
    headers = {"X-Mock-Role": "CITIZEN", "X-Mock-User": "usr-citizen-001"}
    response = await client.post(
        "/api/v1/alerts/draft", json={"headline": "Fake Alert"}, headers=headers
    )
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "FORBIDDEN"
