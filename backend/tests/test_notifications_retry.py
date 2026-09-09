import pytest
from httpx import AsyncClient

from app.integrations.notifications.provider import ExpoPushNotificationProvider


@pytest.mark.asyncio
async def test_expo_push_message_builder_and_token_registration(client: AsyncClient):
    provider = ExpoPushNotificationProvider()
    token = "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]"
    alert = {
        "alert_id": "alert-test-001",
        "headline": "Heavy Inundation Warning",
        "description": "Water rising rapidly",
        "severity": "Extreme",
        "urgency": "Immediate",
    }

    # Verify message payload
    msg = provider.build_message(token, alert)
    assert msg["to"] == token
    assert "🚨 Heavy Inundation Warning" in msg["title"]
    assert msg["priority"] == "high"
    assert msg["data"]["alert_id"] == "alert-test-001"

    # Verify send alert returns True in local/test mode
    ok = await provider.send_alert([token], alert)
    assert ok is True

    # Register device token API
    res = await client.post(
        "/api/v1/notifications/device-token", json={"expo_push_token": token, "device_os": "ios"}
    )
    assert res.status_code == 201
    assert res.json()["status"] == "REGISTERED"
