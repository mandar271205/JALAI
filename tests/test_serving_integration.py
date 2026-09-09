"""Integration and contract adherence tests for the JalRakshak ML Serving API (SIH26071)."""
import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient
import jsonschema

from jalrakshak_ml.serving.app import app

client = TestClient(app)
AUTH_HEADER = {"Authorization": "Bearer dev-ml-token"}

# Locate contracts/schemas in backend repository
BACKEND_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "sih backend" / "contracts" / "schemas"


def test_health_check():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_unauthenticated_request_rejected():
    res = client.post("/internal/v1/nowcast", json={})
    assert res.status_code == 401

    res_bad = client.post("/internal/v1/nowcast", json={}, headers={"Authorization": "Bearer wrong-token"})
    assert res_bad.status_code == 403


def test_canonical_nowcast_endpoint_and_schema_conformance():
    res = client.post(
        "/internal/v1/nowcast",
        json={"lead_time_minutes": 120, "temporal_step_minutes": 30},
        headers=AUTH_HEADER,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["model_version"] == "pysteps-lk-v1"
    assert data["lead_time_minutes"] == 120
    assert data["units"] == "mm/h"
    assert len(data["bounds"]) == 4
    # Scientific honesty: synthetic demo input flagged
    assert data["operational_real_data"] is False
    assert data["input_source"] == "synthetic_demo_frames"
    # Scientific safety: quality score and confidence are separate
    assert "quality_score" in data
    assert "confidence" in data
    assert data["quality_score"] == 0.98

    # Validate against backend nowcast-manifest.schema.json
    schema_path = BACKEND_SCHEMAS_DIR / "nowcast-manifest.schema.json"
    if schema_path.exists():
        with open(schema_path) as f:
            schema = json.load(f)
        jsonschema.validate(instance=data, schema=schema)


def test_canonical_inundation_endpoint_and_schema_conformance():
    res = client.post(
        "/internal/v1/inundation",
        json={"valid_time": "2026-09-09T10:00:00Z"},
        headers=AUTH_HEADER,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["model_version"] == "hydro-susceptibility-v1"
    # Scientific safety: physical depth in meters is uncalibrated, so max_depth_meters is None
    assert data["max_depth_meters"] is None
    assert data["is_physically_calibrated"] is False
    assert data["depth_unit"] == "relative_inundation_index"
    assert data["relative_inundation_index"] == 0.82
    assert "depth_cog_url" in data
    assert "velocity_cog_url" in data

    # Validate against backend inundation-manifest.schema.json (omitting null max_depth_meters)
    schema_path = BACKEND_SCHEMAS_DIR / "inundation-manifest.schema.json"
    if schema_path.exists():
        with open(schema_path) as f:
            schema = json.load(f)
        filtered = {k: v for k, v in data.items() if v is not None}
        jsonschema.validate(instance=filtered, schema=schema)


def test_canonical_risk_endpoint_and_schema_conformance():
    res = client.post(
        "/internal/v1/risk",
        json={"bbox": "72.75,18.88,73.02,19.28"},
        headers=AUTH_HEADER,
    )
    assert res.status_code == 200
    data = res.json()
    assert "cells" in data
    assert len(data["cells"]) > 0
    assert data["validated_hev_risk"] is False
    assert data["risk_calculation_type"] == "topographic_susceptibility_heuristic"

    schema_path = BACKEND_SCHEMAS_DIR / "risk-cell.schema.json"
    if schema_path.exists():
        with open(schema_path) as f:
            schema = json.load(f)
        for cell in data["cells"]:
            # Scientific safety: uncalibrated physical depth is None
            assert cell["flood_depth_m"] is None
            jsonschema.validate(instance=cell, schema=schema)
            assert cell["risk_level"] in ["LOW", "MODERATE", "HIGH", "SEVERE"]
            assert 0.0 <= cell["confidence"] <= 1.0


def test_canonical_report_verification():
    res = client.post(
        "/internal/v1/report-verification",
        json={
            "report_id": "rep-test-101",
            "image_url": "http://minio/photo.jpg",
            "description": "Severe waterlogging near Kurla station, water above knee level",
        },
        headers=AUTH_HEADER,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["report_id"] == "rep-test-101"
    assert data["verification_status"] == "AI_VERIFIED"
    assert data["verification_state"] == "HEURISTIC"
    assert data["is_calibrated"] is False
    # Scientific safety: fabricated physical depth removed
    assert data["detected_water_level_cm"] is None
    assert data["is_flood_related"] is True
    assert len(data["warnings"]) > 0


def test_models_status_and_runs():
    status_res = client.get("/internal/v1/models/status", headers=AUTH_HEADER)
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["status"] == "HEALTHY"
    assert "nowcasting" in status_data["models"]
    assert status_data["models"]["nowcasting"]["version"] == "pysteps-lk-v1"

    # Trigger nowcast to generate a run_id
    nowcast_res = client.post("/internal/v1/nowcast", json={}, headers=AUTH_HEADER)
    manifest = nowcast_res.json()
    run_id = manifest["provenance"]["run_id"]

    run_res = client.get(f"/internal/v1/runs/{run_id}", headers=AUTH_HEADER)
    assert run_res.status_code == 200
    assert run_res.json()["run_id"] == run_id


def test_teammate_backend_alias_routes():
    # 1. /internal/ml/nowcast
    r1 = client.post("/internal/ml/nowcast", json={}, headers=AUTH_HEADER)
    assert r1.status_code == 200
    assert "cog_url" in r1.json()

    # 2. /internal/ml/inundation
    r2 = client.post("/internal/ml/inundation", json={}, headers=AUTH_HEADER)
    assert r2.status_code == 200
    assert "depth_cog_url" in r2.json()
    assert r2.json()["max_depth_meters"] is None

    # 3. /internal/ml/risk-assessment
    r3 = client.post("/internal/ml/risk-assessment", json={}, headers=AUTH_HEADER)
    assert r3.status_code == 200
    assert "cells" in r3.json()

    # 4. /internal/ml/verify-report
    r4 = client.post(
        "/internal/ml/verify-report",
        json={"report_id": "rep-alias-01", "image_url": "http://photo.jpg", "description": "street flood"},
        headers=AUTH_HEADER,
    )
    assert r4.status_code == 200
    assert r4.json()["verification_status"] == "AI_VERIFIED"
    assert r4.json()["detected_water_level_cm"] is None
