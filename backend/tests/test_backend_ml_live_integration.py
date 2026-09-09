"""End-to-end integration tests verifying Backend communication with the ML service contract.

Strict architectural boundary:
Does NOT import PyTorch or jalrakshak_ml into the backend environment.
Tests HttpMLProvider against authentic ML service responses, validates circuit breaking,
and tests public API endpoints with live ML provider active.
"""
import json
import pytest
from httpx import MockTransport, Request, Response
from starlette.testclient import TestClient

from app.core.config import get_settings
from app.integrations.ml.circuit_breaker import CircuitState
from app.integrations.ml.http_provider import HttpMLProvider
from app.integrations.ml.provider import StubMLProvider, get_ml_provider
from app.main import app as backend_app


# Authentic ML service payloads as returned by jalrakshak_ml.serving.app
SAMPLE_NOWCAST_RESPONSE = {
    "manifest_id": "manifest-nowcast-live-01",
    "generated_at": "2026-09-09T10:00:00Z",
    "valid_from": "2026-09-09T10:00:00Z",
    "valid_to": "2026-09-09T12:00:00Z",
    "lead_time_minutes": 120,
    "cog_url": "http://localhost:9000/jalrakshak/rasters/nowcast_latest.tif",
    "bounds": [72.75, 18.88, 73.02, 19.28],
    "model_version": "pysteps-lk-v1",
    "data_version": "gpm-imerg-v07-mumbai",
    "units": "mm/h",
    "shape": [4, 256, 256],
    "forecast_type": "deterministic",
    "quality_score": 0.98,
    "confidence": 0.92,
    "provenance": {"provider": "pysteps_lucaskanade"},
}

SAMPLE_INUNDATION_RESPONSE = {
    "manifest_id": "manifest-inundation-live-01",
    "generated_at": "2026-09-09T10:00:00Z",
    "valid_time": "2026-09-09T10:30:00Z",
    "depth_cog_url": "http://localhost:9000/jalrakshak/rasters/flood_depth_latest.tif",
    "velocity_cog_url": "http://localhost:9000/jalrakshak/rasters/flood_velocity_latest.tif",
    "max_depth_meters": None,
    "relative_inundation_index": 0.82,
    "model_version": "hydro-susceptibility-v1",
    "data_version": "dem-nasadem-srtm30",
    "is_physically_calibrated": False,
    "depth_unit": "relative_inundation_index",
    "quality_score": 0.95,
    "confidence": 0.88,
}

SAMPLE_RISK_RESPONSE = {
    "run_id": "risk-live-01",
    "model_version": "v1.2.0-hydro",
    "data_version": "mumbai-multisource-20260909",
    "issue_time": "2026-09-09T10:00:00Z",
    "valid_time": "2026-09-09T10:00:00Z",
    "risk_calculation_type": "topographic_susceptibility_heuristic",
    "validated_hev_risk": False,
    "cells": [
        {
            "h3_cell_id": "8860145b53fffff",
            "valid_time": "2026-09-09T10:00:00Z",
            "risk_level": "SEVERE",
            "confidence": 0.94,
            "flood_depth_m": None,  # Physical depth uncalibrated
            "rainfall_rate_mm_h": 68.5,
            "ward_id": "WARD-12-DHARAVI",
            "model_version": "v1.2.0-hydro",
            "data_version": "mumbai-multisource-20260909",
        },
        {
            "h3_cell_id": "8860145b51fffff",
            "valid_time": "2026-09-09T10:00:00Z",
            "risk_level": "HIGH",
            "confidence": 0.91,
            "flood_depth_m": None,  # Physical depth uncalibrated
            "rainfall_rate_mm_h": 54.0,
            "ward_id": "WARD-L-KURLA",
            "model_version": "v1.2.0-hydro",
            "data_version": "mumbai-multisource-20260909",
        },
    ],
}

SAMPLE_VERIFY_RESPONSE = {
    "report_id": "rep-smoke-01",
    "verification_status": "AI_VERIFIED",
    "verification_state": "HEURISTIC",
    "ai_confidence": 0.5,
    "detected_water_level_cm": None,  # Unsupported physical depth is None
    "is_flood_related": True,
    "model_version": "heuristic-keyword-verifier-v1",
}


def mock_ml_handler(request: Request) -> Response:
    path = request.url.path
    auth = request.headers.get("authorization", "")
    if auth != "Bearer dev-ml-token":
        return Response(403, json={"detail": "Invalid internal ML service token"})

    if path in ("/internal/ml/nowcast", "/internal/v1/nowcast"):
        return Response(200, json=SAMPLE_NOWCAST_RESPONSE)
    elif path in ("/internal/ml/inundation", "/internal/v1/inundation"):
        return Response(200, json=SAMPLE_INUNDATION_RESPONSE)
    elif path in ("/internal/ml/risk-assessment", "/internal/v1/risk"):
        return Response(200, json=SAMPLE_RISK_RESPONSE)
    elif path in ("/internal/ml/verify-report", "/internal/v1/report-verification"):
        return Response(200, json=SAMPLE_VERIFY_RESPONSE)
    elif path == "/health":
        return Response(200, json={"status": "ok"})
    return Response(404, json={"detail": "Not found"})


@pytest.fixture
def live_mock_provider():
    transport = MockTransport(mock_ml_handler)
    return HttpMLProvider(
        base_url="http://localhost:8001",
        auth_token="dev-ml-token",
        fallback_stub=StubMLProvider(),
        transport=transport,
    )


@pytest.mark.asyncio
async def test_backend_ml_provider_nowcast_live(live_mock_provider):
    data = await live_mock_provider.get_nowcast_manifest()
    assert data["model_version"] == "pysteps-lk-v1"
    assert data["units"] == "mm/h"
    assert data["lead_time_minutes"] == 120
    assert len(data["bounds"]) == 4
    # Provenance: quality score and confidence are separate
    assert data["quality_score"] == 0.98
    assert data["confidence"] == 0.92
    assert data.get("is_fallback") is False


@pytest.mark.asyncio
async def test_backend_ml_provider_inundation_live(live_mock_provider):
    data = await live_mock_provider.get_inundation_manifest()
    assert data["model_version"] == "hydro-susceptibility-v1"
    assert data["is_physically_calibrated"] is False
    assert data.get("max_depth_meters") is None
    assert "depth_cog_url" in data
    assert "velocity_cog_url" in data
    assert data.get("is_fallback") is False


@pytest.mark.asyncio
async def test_backend_ml_provider_risk_cells_live(live_mock_provider):
    cells = await live_mock_provider.get_risk_cells()
    assert len(cells) == 2
    assert cells[0]["ward_id"] == "WARD-12-DHARAVI"
    assert cells[0]["risk_level"] == "SEVERE"
    assert cells[0].get("flood_depth_m") is None
    assert len(cells[0]["h3_cell_id"]) == 15


@pytest.mark.asyncio
async def test_backend_ml_provider_verify_report_live(live_mock_provider):
    verif = await live_mock_provider.verify_report(
        report_id="rep-smoke-01",
        image_url="http://minio/flood.jpg",
        description="Severe flooding near Kurla",
    )
    assert verif["verification_status"] == "AI_VERIFIED"
    assert verif["verification_state"] == "HEURISTIC"
    assert verif["detected_water_level_cm"] is None
    assert verif.get("is_fallback") is False


@pytest.mark.asyncio
async def test_public_nowcast_api_with_live_provider(live_mock_provider):
    backend_app.dependency_overrides[get_ml_provider] = lambda: live_mock_provider
    client = TestClient(backend_app)
    try:
        res = client.get("/api/v1/nowcast/manifest")
        assert res.status_code == 200
        data = res.json()
        assert data["model_version"] == "pysteps-lk-v1"
        assert "cog_url" in data
    finally:
        backend_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_public_risk_api_with_live_provider(live_mock_provider):
    backend_app.dependency_overrides[get_ml_provider] = lambda: live_mock_provider
    client = TestClient(backend_app)
    try:
        res = client.get("/api/v1/risk/cells")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 2
        assert data["items"][0]["h3_cell_id"] == "8860145b53fffff"
    finally:
        backend_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_circuit_breaker_graceful_fallback_when_ml_offline():
    offline_provider = HttpMLProvider(
        base_url="http://127.0.0.1:59998",
        auth_token="test-token",
        timeout_seconds=0.2,
        fallback_stub=StubMLProvider(),
    )
    # Failures trip circuit breaker to OPEN, falling back to stub
    for _ in range(3):
        res = await offline_provider.get_nowcast_manifest()
        assert "manifest_id" in res
        assert res.get("is_fallback") is True

    assert offline_provider.circuit_breaker.state == CircuitState.OPEN
    fast_fallback = await offline_provider.get_nowcast_manifest()
    assert "manifest_id" in fast_fallback
    assert fast_fallback.get("is_fallback") is True
    assert fast_fallback.get("fallback_reason") == "circuit_breaker_open"


@pytest.mark.asyncio
async def test_failure_modes_and_explicit_fallback_tagging():
    """Verify backend fallback behavior for 401, 500, and malformed responses."""
    # 1. 401 Unauthorized handler
    def handler_401(request: Request) -> Response:
        return Response(401, json={"detail": "Unauthorized"})

    p_401 = HttpMLProvider(
        base_url="http://localhost:8001",
        auth_token="bad-token",
        fallback_stub=StubMLProvider(),
        transport=MockTransport(handler_401),
    )
    res_401 = await p_401.get_nowcast_manifest()
    assert res_401.get("is_fallback") is True
    assert res_401.get("fallback_reason") == "ml_service_offline_or_error"

    # 2. 500 Internal Server Error handler
    def handler_500(request: Request) -> Response:
        return Response(500, json={"detail": "Internal Server Error"})

    p_500 = HttpMLProvider(
        base_url="http://localhost:8001",
        auth_token="token",
        fallback_stub=StubMLProvider(),
        transport=MockTransport(handler_500),
    )
    res_500 = await p_500.get_inundation_manifest()
    assert res_500.get("is_fallback") is True
    assert res_500.get("is_physically_calibrated") is False
    assert res_500.get("max_depth_meters") is None

    # 3. Malformed non-JSON response handler
    def handler_malformed(request: Request) -> Response:
        return Response(200, content=b"INVALID_NOT_JSON{")

    p_malformed = HttpMLProvider(
        base_url="http://localhost:8001",
        auth_token="token",
        fallback_stub=StubMLProvider(),
        transport=MockTransport(handler_malformed),
    )
    res_malformed = await p_malformed.verify_report("rep-1", None, "flood")
    assert res_malformed.get("is_fallback") is True
    assert res_malformed.get("detected_water_level_cm") is None
