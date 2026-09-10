"""Comprehensive Integration Tests for Web Dashboard and Mobile App Endpoints,
Groq Vision Corroboration, and Map/GIS queries.
"""

import base64
import pytest
from httpx import AsyncClient

from app.integrations.ai.vision_service import GroqVisionService

# Minimal valid 1x1 white JPEG image base64 encoded
TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
)


def _generate_test_image_b64() -> str:
    """Return valid test JPEG image base64."""
    return TINY_JPEG_B64


@pytest.mark.asyncio
async def test_mobile_home_endpoint(client: AsyncClient):
    """Test mobile single-call aggregation endpoint returns rich home payload."""
    res = await client.get("/api/v1/mobile/home?lat=19.0760&lon=72.8777&radius_km=5.0")
    assert res.status_code == 200
    data = res.json()

    assert "location" in data
    assert data["location"]["latitude"] == 19.0760
    assert data["location"]["longitude"] == 72.8777

    assert "current_risk" in data
    assert data["current_risk"]["risk_level"] in ("LOW", "MODERATE", "HIGH", "SEVERE")
    assert "dominant_factors" in data["current_risk"]

    assert "rainfall_outlook" in data
    assert len(data["rainfall_outlook"]) == 4
    horizons = [item["lead_time_minutes"] for item in data["rainfall_outlook"]]
    assert horizons == [30, 60, 90, 120]
    for item in data["rainfall_outlook"]:
        # Regression: numeric rainfall values MUST NOT be invented
        assert item["rainfall_intensity_mm_h"] is None
        assert item["status"] == "UNAVAILABLE"

    assert "active_alerts" in data
    assert "nearby_incidents" in data
    assert "nearby_reports" in data
    assert "watched_locations" in data
    assert "system_status" in data
    assert data["system_status"]["operational_mode"] == "DEMO_FIXTURE"
    assert data["system_status"]["is_radar_available"] is False


@pytest.mark.asyncio
async def test_dashboard_summary_role_security(client: AsyncClient):
    """Test dashboard summary endpoint strictly enforces RBAC authorization."""
    # 1. Citizen role is forbidden
    citizen_headers = {"X-User-Role": "CITIZEN", "X-User-ID": "cit-001"}
    cit_res = await client.get("/api/v1/dashboard/summary", headers=citizen_headers)
    assert cit_res.status_code in (401, 403)

    # 2. Municipal Officer role is authorized
    officer_headers = {"X-User-Role": "MUNICIPAL_OFFICER", "X-User-ID": "off-001"}
    off_res = await client.get("/api/v1/dashboard/summary", headers=officer_headers)
    assert off_res.status_code == 200
    data = off_res.json()

    assert "kpis" in data
    kpis = data["kpis"]
    assert "high_severe_risk_cells_count" in kpis
    assert "active_incidents_count" in kpis
    assert "unverified_reports_count" in kpis
    assert "critical_assets_at_risk_count" in kpis
    assert "active_alerts_count" in kpis
    assert "active_responders_count" in kpis

    assert "city_risk_status" in data
    assert "model_health" in data
    # Strict scientific claim gates check:
    assert data["model_health"]["rainfall_winner_frozen"] is False
    assert data["model_health"]["fno_validated"] is False


@pytest.mark.asyncio
async def test_map_gis_endpoints(client: AsyncClient):
    """Test map endpoints support spatial bounding box queries."""
    bbox = "72.75,18.88,73.05,19.28"

    # 1. Risk map
    risk_res = await client.get(f"/api/v1/map/risk?bbox={bbox}&min_level=MODERATE")
    assert risk_res.status_code == 200
    risk_data = risk_res.json()
    assert risk_data["type"] == "RiskCellCollection"
    assert "features" in risk_data

    # 2. Incidents map
    inc_res = await client.get(f"/api/v1/map/incidents?bbox={bbox}")
    assert inc_res.status_code == 200
    inc_data = inc_res.json()
    assert inc_data["type"] == "IncidentCollection"

    # 3. Reports map
    rep_res = await client.get(f"/api/v1/map/reports?bbox={bbox}")
    assert rep_res.status_code == 200
    rep_data = rep_res.json()
    assert rep_data["type"] == "FieldReportCollection"

    # 4. Assets map
    asset_res = await client.get(f"/api/v1/map/assets?bbox={bbox}")
    assert asset_res.status_code == 200
    asset_data = asset_res.json()
    assert asset_data["type"] == "CriticalAssetCollection"

    # 5. Alerts map
    alert_res = await client.get("/api/v1/map/alerts")
    assert alert_res.status_code == 200
    alert_data = alert_res.json()
    assert alert_data["type"] == "AlertCollection"


@pytest.mark.asyncio
async def test_citizen_report_full_lifecycle_and_vision_corroboration(client: AsyncClient):
    """Test complete citizen reporting flow: draft -> upload intent -> complete -> status -> detail."""
    img_b64 = _generate_test_image_b64()

    # 1. Create draft report
    draft_res = await client.post(
        "/api/v1/reports/draft",
        json={
            "latitude": 19.0728,
            "longitude": 72.8711,
            "description": "Rising floodwater on main road under bridge",
        },
    )
    assert draft_res.status_code == 201
    draft_data = draft_res.json()
    report_id = draft_data["report_id"]
    assert draft_data["verification_status"] == "DRAFT"

    # 2. Generate signed upload intent via RESTful path
    upload_res = await client.post(
        f"/api/v1/reports/{report_id}/uploads",
        json={
            "filename": "water_bridge.jpg",
            "content_type": "image/jpeg",
            "file_size_bytes": 10240,
        },
    )
    assert upload_res.status_code == 201
    upload_data = upload_res.json()
    upload_id = upload_data["upload_id"]
    assert "presigned_url" in upload_data
    assert upload_data["status"] == "PENDING"

    # 3. Complete upload with image base64 triggering vision corroboration
    complete_res = await client.post(
        f"/api/v1/reports/{report_id}/uploads/complete",
        json={
            "upload_id": upload_id,
            "sha256_checksum": "synthetic-test-checksum-12345",
            "file_content_base64": img_b64,
            "content_type": "image/jpeg",
        },
    )
    assert complete_res.status_code == 200
    comp_data = complete_res.json()
    assert comp_data["status"] == "FINALIZED"
    assert comp_data["verification_status"] == "AI_VERIFIED"
    assert "visual_corroboration" in comp_data
    if comp_data["visual_corroboration"]:
        # Strict scientific sanctity: exact_depth_m MUST be None
        assert comp_data["visual_corroboration"]["exact_depth_m"] is None

    # 4. Fast polling status check
    status_res = await client.get(f"/api/v1/reports/{report_id}/status")
    assert status_res.status_code == 200
    st_data = status_res.json()
    assert st_data["report_id"] == report_id
    assert st_data["verification_status"] == "AI_VERIFIED"

    # 5. Full detail query
    detail_res = await client.get(f"/api/v1/reports/{report_id}")
    assert detail_res.status_code == 200
    det_data = detail_res.json()
    assert det_data["report_id"] == report_id
    assert det_data["verification_status"] == "AI_VERIFIED"
    assert det_data["estimated_water_depth_cm"] is None  # Uncalibrated depth is never fabricated

    # 6. List reports query includes our report
    list_res = await client.get(f"/api/v1/reports?status=AI_VERIFIED&limit=10")
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(r["report_id"] == report_id for r in items)


@pytest.mark.asyncio
async def test_device_push_token_lifecycle(client: AsyncClient):
    """Test registering and unregistering mobile push notification device tokens."""
    token_str = "ExponentPushToken[synthetic-test-token-777]"

    # 1. Register token
    reg_res = await client.post(
        "/api/v1/devices/push-token",
        json={"token": token_str, "device_os": "android", "device_id": "device-pixel-001"},
    )
    assert reg_res.status_code == 201
    assert reg_res.json()["status"] == "REGISTERED"

    # 2. Unregister token
    del_res = await client.delete("/api/v1/devices/push-token/device-pixel-001")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "UNREGISTERED"


@pytest.mark.asyncio
async def test_watch_locations_crud(client: AsyncClient):
    """Test watch locations full CRUD including PATCH."""
    # 1. Create location
    create_res = await client.post(
        "/api/v1/watch-locations",
        json={
            "label": "Office BKC",
            "latitude": 19.0657,
            "longitude": 72.8687,
            "risk_threshold": "SEVERE",
            "notify_push": True,
        },
    )
    assert create_res.status_code == 201
    loc = create_res.json()
    loc_id = loc["location_id"]
    assert loc["label"] == "Office BKC"

    # 2. List locations
    list_res = await client.get("/api/v1/watch-locations")
    assert list_res.status_code == 200
    assert any(l["location_id"] == loc_id for l in list_res.json())

    # 3. Patch location
    patch_res = await client.patch(
        f"/api/v1/watch-locations/{loc_id}",
        json={"label": "Headquarters BKC", "risk_threshold": "HIGH"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["label"] == "Headquarters BKC"
    assert patch_res.json()["risk_threshold"] == "HIGH"

    # 4. Delete location
    del_res = await client.delete(f"/api/v1/watch-locations/{loc_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "DELETED"


@pytest.mark.asyncio
async def test_groq_vision_service_fallback():
    """Verify Groq Vision service gracefully falls back without uncaught exceptions."""
    service = GroqVisionService(api_key="synthetic_invalid_key_for_testing", timeout_seconds=1.0)
    res = await service.analyze_image(
        image_bytes=b"fake-image-bytes-not-real-jpg",
        user_context="Unit test fallback validation",
    )
    assert isinstance(res, dict)
    assert res["is_fallback"] is True
    assert res["exact_depth_m"] is None
    assert len(res["warnings"]) > 0
