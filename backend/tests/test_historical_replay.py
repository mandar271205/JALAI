import pytest
from starlette.testclient import TestClient

from app.domains.replay.manifest import HISTORICAL_REPLAY_MANIFEST
from app.domains.replay.session import ReplaySessionManager
from app.main import app


def test_immutable_replay_manifest_structure():
    assert "replay_id" in HISTORICAL_REPLAY_MANIFEST
    assert HISTORICAL_REPLAY_MANIFEST["is_replay_isolated"] is True
    assert "precomputed_tile_manifests" in HISTORICAL_REPLAY_MANIFEST

    timesteps = HISTORICAL_REPLAY_MANIFEST["timesteps"]
    assert len(timesteps) >= 3

    for ts in timesteps:
        assert "timestamp" in ts
        assert "weather" in ts
        assert "model_outputs" in ts
        assert "risk_snapshot" in ts
        assert "reports" in ts
        assert "incidents" in ts
        assert "alerts" in ts
        assert "tile_manifest" in ts
        assert ts["weather"]["rainfall_rate_mm_h"] >= 0
        assert ts["model_outputs"]["max_predicted_depth_m"] >= 0


def test_virtual_replay_clock_controls():
    manager = ReplaySessionManager()
    session = manager.create_session(playback_speed=2.0)
    session_id = session["session_id"]

    assert session["status"] == "PAUSED"
    assert session["playback_speed"] == 2.0
    assert session["is_replay_isolated"] is True

    # Play
    played = manager.control_playback(session_id, "PLAY")
    assert played["status"] == "PLAYING"

    # Step forward
    stepped = manager.control_playback(session_id, "STEP_FORWARD")
    assert stepped["status"] == "PAUSED"
    assert stepped["current_timestep_index"] == 1

    # Scrub to middle timestamp
    scrubbed = manager.scrub_to_timestamp(session_id, "2025-07-26T12:00:00Z")
    assert scrubbed["simulated_time"] == "2025-07-26T12:00:00Z"

    # Get slice
    slice_data = manager.get_current_slice(session_id)
    assert slice_data["session"]["session_id"] == session_id
    assert slice_data["temporal_slice"]["timestamp"] == "2025-07-26T12:00:00Z"
    assert len(slice_data["temporal_slice"]["incidents"]) > 0

    # Reset
    reset = manager.control_playback(session_id, "RESET")
    assert reset["current_timestep_index"] == 0
    assert reset["simulated_time"] == session["start_time"]


def test_replay_scrub_out_of_bounds_validation():
    manager = ReplaySessionManager()
    session = manager.create_session()
    session_id = session["session_id"]

    with pytest.raises(Exception):
        manager.scrub_to_timestamp(session_id, "1999-01-01T00:00:00Z")


def test_predicted_vs_observed_metrics():
    metrics = HISTORICAL_REPLAY_MANIFEST["predicted_vs_observed_metrics"]
    assert metrics["rmse_water_depth_meters"] < 0.20
    assert metrics["iou_inundation_extent"] >= 0.85
    assert metrics["validation_status"] == "CALIBRATED_BENCHMARK_VERIFIED"


def test_replay_api_endpoints():
    client = TestClient(app)

    # 1. Manifest
    r = client.get("/api/v1/replay/manifest")
    assert r.status_code == 200
    data = r.json()
    assert data["replay_id"] == "mumbai_cloudburst_20250726"

    # 2. Create session
    r = client.post("/api/v1/replay/sessions", json={"playback_speed": 1.5})
    assert r.status_code == 201
    sess = r.json()
    sid = sess["session_id"]
    assert sess["playback_speed"] == 1.5

    # 3. Control session
    r = client.post(f"/api/v1/replay/sessions/{sid}/control", json={"action": "STEP_FORWARD"})
    assert r.status_code == 200
    assert r.json()["current_timestep_index"] == 1

    # 4. State
    r = client.get(f"/api/v1/replay/sessions/{sid}/state")
    assert r.status_code == 200
    state = r.json()
    assert "temporal_slice" in state
    assert "predicted_vs_observed_metrics" in state

    # 5. Metrics
    r = client.get("/api/v1/replay/metrics")
    assert r.status_code == 200
    assert r.json()["iou_inundation_extent"] >= 0.85
