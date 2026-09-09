import base64
from datetime import UTC, datetime, timedelta

import jwt
from starlette.testclient import TestClient

from app.core.config import get_settings
from app.core.security_hardening import (
    ClamAVStubScanner,
    rate_limiter,
    sanitize_sensitive_data,
)
from app.domains.incidents.state_machine import IncidentStatus
from app.domains.responders.service import responder_service
from app.main import app

settings = get_settings()


def test_secure_response_headers():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains; preload"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_privilege_escalation_denied():
    client = TestClient(app)

    # 1. Citizen attempts alert publishing
    r1 = client.post("/api/v1/alerts/alt-fake/publish", headers={"X-Mock-Role": "CITIZEN"})
    assert r1.status_code == 403

    # 2. Citizen attempts resource plan approval
    r2 = client.post(
        "/api/v1/optimization/approve-plan", json={}, headers={"X-Mock-Role": "CITIZEN"}
    )
    assert r2.status_code == 403

    # 3. Citizen attempts model activation
    r3 = client.post("/api/v1/models/activate", json={}, headers={"X-Mock-Role": "CITIZEN"})
    assert r3.status_code == 403


def test_cross_region_access_denied():
    client = TestClient(app)

    # Create incident in Mumbai
    create_resp = client.post(
        "/api/v1/incidents",
        json={
            "title": "Mumbai Flood",
            "category": "WATERLOGGING",
            "latitude": 19.07,
            "longitude": 72.87,
            "severity": "HIGH",
            "region": "mumbai",
        },
        headers={"X-Mock-Role": "DISASTER_MANAGER", "X-Mock-User": "mumbai_officer"},
    )
    assert create_resp.status_code == 201
    inc_id = create_resp.json()["incident_id"]

    # Pune officer attempts to transition Mumbai incident
    client_pune = TestClient(app)
    # Use AuthenticatedUser metadata via mock
    from app.core.security import AuthenticatedUser, UserRole, get_current_user

    async def mock_pune_user():
        return AuthenticatedUser(
            user_id="pune-officer-01",
            role=UserRole.MUNICIPAL_OFFICER,
            metadata={"region": "pune"},
        )

    app.dependency_overrides[get_current_user] = mock_pune_user
    try:
        r = client_pune.post(
            f"/api/v1/incidents/{inc_id}/transition",
            json={"target_status": IncidentStatus.OPEN.value, "reason": "Officer opening ticket"},
        )
        assert r.status_code == 403
        assert "Region-scoped RBAC violation" in r.json()["error"]["message"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_expired_jwt_rejected():
    client = TestClient(app)
    # Generate expired JWT
    expired_payload = {
        "sub": "usr-attacker-01",
        "role": "ADMIN",
        "exp": datetime.now(UTC) - timedelta(hours=2),
        "aud": "authenticated",
    }
    expired_token = jwt.encode(expired_payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    r = client.get("/api/v1/audit/logs", headers={"Authorization": f"Bearer {expired_token}"})
    assert r.status_code == 401
    assert "Signature has expired" in r.json()["error"]["message"]


def test_malformed_jwt_rejected():
    client = TestClient(app)
    r = client.get(
        "/api/v1/audit/logs",
        headers={"Authorization": "Bearer not.a.valid.jwt.signature.gibberish"},
    )
    assert r.status_code == 401
    assert "Invalid authentication token" in r.json()["error"]["message"]


def test_file_spoofing_rejected():
    client = TestClient(app)

    # Executable bytes disguised as image/jpeg
    executable_script = b"#!/bin/bash\nrm -rf /"
    encoded = base64.b64encode(executable_script).decode("utf-8")

    r = client.post(
        "/api/v1/reports/upload-finalize",
        json={
            "upload_id": "up-spoof-01",
            "content_type": "image/jpeg",
            "file_content_base64": encoded,
            "filename": "innocent_photo.jpg",
        },
        headers={"X-Mock-Role": "CITIZEN"},
    )
    assert r.status_code == 422
    assert "File spoofing detected" in r.json()["error"]["message"]


def test_malware_scanning_detects_eicar():
    client = TestClient(app)

    # Valid JPEG header followed by EICAR test string
    eicar_content = b"\xff\xd8\xff\xe0" + ClamAVStubScanner.EICAR_SIGNATURE
    encoded = base64.b64encode(eicar_content).decode("utf-8")

    r = client.post(
        "/api/v1/reports/upload-finalize",
        json={
            "upload_id": "up-malware-01",
            "content_type": "image/jpeg",
            "file_content_base64": encoded,
            "filename": "infected_photo.jpg",
        },
        headers={"X-Mock-Role": "CITIZEN"},
    )
    assert r.status_code == 422
    assert "Malicious content detected" in r.json()["error"]["message"]


def test_oversized_upload_rejected():
    client = TestClient(app)
    # Send request with oversized Content-Length header (> 10MB)
    r = client.post(
        "/api/v1/reports/upload-intent",
        headers={"Content-Length": str(15 * 1024 * 1024)},
        content=b"x" * 100,
    )
    assert r.status_code == 413
    assert "Payload Too Large" in r.json()["error"]


def test_rate_limit_abuse():
    client = TestClient(app)
    # Temporarily set rate limit to 5 requests for deterministic testing
    original_max = rate_limiter.max_requests
    rate_limiter.max_requests = 5
    rate_limiter.reset()

    try:
        # First 5 succeed
        for _ in range(5):
            r = client.get("/health")
            assert r.status_code == 200

        # 6th request triggers HTTP 429
        abuse_resp = client.get("/health")
        assert abuse_resp.status_code == 429
        assert "Too Many Requests" in abuse_resp.json()["error"]
        assert "Retry-After" in abuse_resp.headers
    finally:
        rate_limiter.max_requests = original_max
        rate_limiter.reset()


def test_unauthorized_alert_publishing_denied():
    client = TestClient(app)
    r = client.post(
        "/api/v1/alerts/draft",
        json={
            "severity": "Extreme",
            "headline": "Citizen Alert",
            "instruction": "Test",
        },
        headers={"X-Mock-Role": "CITIZEN"},
    )
    assert r.status_code == 403


def test_responder_task_takeover_prevented_by_optimistic_locking():
    # Create task
    task = responder_service.create_task(
        incident_id="inc-lock-01",
        responder_id="resp-01",
        task_type="MEASURE_DEPTH",
    )
    task_id = task["task_id"]

    # First responder successfully completes
    client = TestClient(app)
    r1 = client.post(
        f"/api/v1/responders/tasks/{task_id}/action",
        json={"action": "MEASURE_DEPTH", "base_version": 1, "measured_depth_cm": 45},
        headers={"X-Mock-Role": "FIELD_RESPONDER"},
    )
    assert r1.status_code == 200
    assert r1.json()["version"] == 2

    # Second responder with stale base_version=1 attempts to update
    r2 = client.post(
        f"/api/v1/responders/tasks/{task_id}/action",
        json={"action": "ROAD_BLOCKED", "base_version": 1},
        headers={"X-Mock-Role": "FIELD_RESPONDER"},
    )
    assert r2.status_code == 409  # Conflict! Optimistic lock failure


def test_log_redaction_and_pii_minimization():
    raw_log = "User logged in with Bearer eyJhbGciOiJIUzI1Ni.secret.token and password=SuperSecretPass! Aadhaar: 1234 5678 9012, phone: 9876543210"
    sanitized = sanitize_sensitive_data(raw_log)
    assert "SuperSecretPass!" not in sanitized
    assert "1234 5678 9012" not in sanitized
    assert "9876543210" not in sanitized
    assert "[REDACTED]" in sanitized
