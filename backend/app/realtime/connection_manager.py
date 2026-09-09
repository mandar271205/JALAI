import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("realtime")


class EventLogEntry:
    def __init__(self, event_id: int, event_type: str, payload: dict[str, Any], timestamp: str):
        self.event_id = event_id
        self.event_type = event_type
        self.payload = payload
        self.timestamp = timestamp

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event": self.event_type,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


class LiveConnectionManager:
    def __init__(self, max_history: int = 1000):
        self.active_connections: list[WebSocket] = []
        self.event_counter: int = 0
        self.event_history: list[EventLogEntry] = []
        self.max_history = max_history

    async def connect(self, websocket: WebSocket, last_event_id: int | None = None):
        await websocket.accept()
        self.active_connections.append(websocket)

        # Reconnection catch-up: replay missed events since last_event_id
        if last_event_id is not None:
            missed = self.get_events_since(last_event_id)
            for event in missed:
                try:
                    await websocket.send_json(event.to_dict())
                except Exception:
                    break

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    def get_events_since(self, last_event_id: int) -> list[EventLogEntry]:
        return [e for e in self.event_history if e.event_id > last_event_id]

    async def broadcast(self, event_type: str, payload: dict[str, Any]) -> EventLogEntry:
        self.event_counter += 1
        now = datetime.now(UTC).isoformat()
        entry = EventLogEntry(
            event_id=self.event_counter, event_type=event_type, payload=payload, timestamp=now
        )

        # Maintain ring buffer
        self.event_history.append(entry)
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)

        # Broadcast to all live clients
        message = entry.to_dict()
        dead_connections = []
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect(ws)

        return entry


live_manager = LiveConnectionManager()
