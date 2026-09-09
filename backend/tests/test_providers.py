import pytest

from app.integrations.ml.provider import StubMLProvider
from app.integrations.notifications.provider import ConsoleNotificationProvider
from app.integrations.object_store.provider import LocalObjectStoreProvider
from app.integrations.routing.provider import StubRoutingProvider


@pytest.mark.asyncio
async def test_stub_ml_provider_determinism():
    provider = StubMLProvider()

    # 1. Nowcast manifest
    nowcast = await provider.get_nowcast_manifest()
    assert "manifest_id" in nowcast
    assert "cog_url" in nowcast
    assert nowcast["lead_time_minutes"] == 120

    # 2. Inundation manifest
    inundation = await provider.get_inundation_manifest()
    assert "manifest_id" in inundation
    assert "depth_cog_url" in inundation

    # 3. Risk cells
    cells = await provider.get_risk_cells()
    assert len(cells) > 0
    assert "h3_cell_id" in cells[0]
    assert cells[0]["risk_level"] in ["LOW", "MODERATE", "HIGH", "SEVERE"]

    # 4. Report verification
    verif = await provider.verify_report("rep-123", "http://example.com/photo.jpg", "flood")
    assert verif["verification_status"] == "AI_VERIFIED"
    assert verif["is_flood_related"] is True


@pytest.mark.asyncio
async def test_console_notification_provider():
    provider = ConsoleNotificationProvider()
    ok_alert = await provider.send_alert(["user-1"], {"headline": "Test Alert"})
    assert ok_alert is True
    ok_dispatch = await provider.send_dispatch("responder-1", {"task_id": "task-1"})
    assert ok_dispatch is True


@pytest.mark.asyncio
async def test_stub_routing_provider():
    provider = StubRoutingProvider()
    route = await provider.compute_lower_risk_route(
        {"latitude": 19.05, "longitude": 72.85}, {"latitude": 19.07, "longitude": 72.87}
    )
    assert route["type"] == "FeatureCollection"
    assert len(route["features"]) > 0
    props = route["features"][0]["properties"]
    assert "distance_meters" in props
    assert props["risk_score"] == "LOW"


@pytest.mark.asyncio
async def test_local_object_store_provider(tmp_path):
    provider = LocalObjectStoreProvider(base_dir=str(tmp_path))
    assert await provider.ensure_bucket() is True

    url = await provider.upload_bytes("test/sample.txt", b"JalRakshak Payload")
    assert url.startswith("file://")

    presigned = await provider.get_presigned_url("test/sample.txt")
    assert presigned.startswith("file://")
