from starlette.testclient import TestClient

from app.main import app
from app.realtime.connection_manager import live_manager


def test_websocket_live_connection_and_heartbeat():
    with TestClient(app) as test_client:
        with test_client.websocket_connect("/api/v1/live") as websocket:
            # 1. Receive initial connection heartbeat
            handshake = websocket.receive_json()
            assert handshake["event"] == "telemetry.heartbeat"
            assert handshake["payload"]["status"] == "CONNECTED"

            # 2. Send ping, expect pong
            websocket.send_json({"type": "ping", "timestamp": "2026-09-08T15:20:00Z"})
            pong = websocket.receive_json()
            assert pong["event"] == "telemetry.heartbeat"
            assert pong["payload"]["type"] == "pong"


def test_websocket_reconnection_with_last_event_id():
    import asyncio

    # Broadcast sample events
    asyncio.run(
        live_manager.broadcast(
            "incident.created", {"incident_id": "inc-ws-100", "title": "Flood Warning"}
        )
    )
    asyncio.run(
        live_manager.broadcast(
            "risk.cell.updated", {"h3_cell": "8860145b53fffff", "level": "SEVERE"}
        )
    )

    last_id = live_manager.event_counter - 1  # Should catch up the last event

    with TestClient(app) as test_client:
        with test_client.websocket_connect(f"/api/v1/live?last_event_id={last_id}") as websocket:
            # First message should be the replayed missed event
            replayed = websocket.receive_json()
            assert replayed["event"] == "risk.cell.updated"
            assert replayed["payload"]["level"] == "SEVERE"

            # Second message is the connection heartbeat
            hb = websocket.receive_json()
            assert hb["event"] == "telemetry.heartbeat"
