import json
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings


class EventBus(ABC):
    @abstractmethod
    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        """Publish event and return unique event stream message ID."""
        pass

    @abstractmethod
    async def get_published_events(self, topic: str) -> list[dict[str, Any]]:
        """Retrieve recent stream events."""
        pass


class InMemoryEventBus(EventBus):
    def __init__(self):
        self._streams: dict[str, list[dict[str, Any]]] = {}

    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        msg_id = f"{int(datetime.now(UTC).timestamp() * 1000)}-{len(self._streams.get(topic, []))}"
        record = {
            "id": msg_id,
            "topic": topic,
            "payload": payload,
            "published_at": datetime.now(UTC).isoformat(),
        }
        self._streams.setdefault(topic, []).append(record)
        return msg_id

    async def get_published_events(self, topic: str) -> list[dict[str, Any]]:
        return self._streams.get(topic, [])


class RedisStreamsEventBus(EventBus):
    """
    Redis Streams event bus implementation.
    Designed with standard topic/partition semantics so it can be swapped to Redpanda without API change.
    """

    def __init__(self, redis_url: str | None = None):
        settings = get_settings()
        self.redis_url = redis_url or settings.REDIS_URL

    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        try:
            r = aioredis.from_url(self.redis_url)
            msg_id = await r.xadd(topic, {"payload": json.dumps(payload)})
            await r.aclose()
            return msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
        except Exception:
            # Fallback to in-memory ID if Redis daemon not running
            return f"local-{uuid.uuid4()}"

    async def get_published_events(self, topic: str) -> list[dict[str, Any]]:
        try:
            r = aioredis.from_url(self.redis_url)
            raw = await r.xrevrange(topic, count=50)
            await r.aclose()
            return [{"id": m[0].decode(), "data": json.loads(m[1][b"payload"])} for m in raw]
        except Exception:
            return []


def get_event_bus() -> EventBus:
    settings = get_settings()
    if settings.APP_ENV == "test":
        return InMemoryEventBus()
    return RedisStreamsEventBus()
