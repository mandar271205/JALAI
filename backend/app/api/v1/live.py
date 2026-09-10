import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.realtime.connection_manager import live_manager

router = APIRouter(tags=["Realtime Live Stream"])
logger = logging.getLogger("api.live")


@router.websocket("/api/v1/live")
@router.websocket("/ws/live")
async def websocket_live_endpoint(
    websocket: WebSocket,
    token: str | None = Query(None),
    last_event_id: int | None = Query(None),
):
    """
    Real-time operational event streaming endpoint over WebSockets.
    Supports reconnection with `last_event_id`, heartbeat ping/pong,
    and events: risk.cell.updated, incident.created, incident.updated,
    report.received, report.verified, source.degraded, model.run.completed.
    """
    # Accept and replay any missed events
    await live_manager.connect(websocket, last_event_id=last_event_id)

    # Send initial connection handshake / heartbeat
    await websocket.send_json(
        {
            "event": "telemetry.heartbeat",
            "timestamp": datetime.now(UTC).isoformat(),
            "payload": {
                "status": "CONNECTED",
                "server_time": datetime.now(UTC).isoformat(),
                "last_event_id": live_manager.event_counter,
            },
        }
    )

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type") or data.get("event")
            if msg_type == "ping":
                await websocket.send_json(
                    {
                        "event": "telemetry.heartbeat",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "payload": {"type": "pong", "client_timestamp": data.get("timestamp")},
                    }
                )
    except WebSocketDisconnect:
        live_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket client error: {e}")
        live_manager.disconnect(websocket)
