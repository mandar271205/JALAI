import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.domains.weather.adapters.base import WeatherSourceAdapter
from app.integrations.object_store.provider import get_object_store_provider
from app.realtime.connection_manager import live_manager

logger = logging.getLogger("weather.ingestion")


class WeatherIngestionPipeline:
    def __init__(self, adapters: list[WeatherSourceAdapter] | None = None):
        self.adapters = adapters or []
        self.object_store = get_object_store_provider()

    async def run_ingestion_cycle(self) -> dict[str, Any]:
        results = {"ingested_count": 0, "degraded_sources": [], "artifacts": []}

        for adapter in self.adapters:
            try:
                # 1. Health check
                health = await adapter.health_check()
                if health.get("status") != "HEALTHY":
                    await self._handle_degradation(adapter.source_id, "Health check failed")
                    results["degraded_sources"].append(adapter.source_id)
                    continue

                # 2. List available items
                items = await adapter.list_available()
                if not items:
                    continue

                for item in items:
                    item_id = item["item_id"]
                    raw_bytes = await adapter.fetch(item_id)
                    checksum = hashlib.sha256(raw_bytes).hexdigest()

                    # 3. Store raw artifact immutably
                    storage_key = f"weather_raw/{adapter.source_id}/{checksum}.bin"
                    raw_uri = await self.object_store.upload_bytes(storage_key, raw_bytes)

                    # 4. Parse metadata & normalize
                    meta = await adapter.parse_metadata(raw_bytes)
                    normalized = await adapter.normalize(raw_bytes)

                    record = {
                        "artifact_id": str(uuid.uuid4()),
                        "source_id": adapter.source_id,
                        "source_timestamp": item.get("timestamp", datetime.now(UTC).isoformat()),
                        "ingested_at": datetime.now(UTC).isoformat(),
                        "sha256_checksum": checksum,
                        "raw_storage_uri": raw_uri,
                        "metadata": meta,
                        "normalized": normalized,
                        "is_immutable": True,
                    }
                    results["artifacts"].append(record)
                    results["ingested_count"] += 1

            except Exception as e:
                logger.error(f"Error ingesting source '{adapter.source_id}': {e}")
                await self._handle_degradation(adapter.source_id, str(e))
                results["degraded_sources"].append(adapter.source_id)

        return results

    async def _handle_degradation(self, source_id: str, reason: str):
        # Graceful degradation: never crash pipeline, emit source.degraded domain event
        logger.warning(f"Weather source degraded: {source_id}, reason: {reason}")
        await live_manager.broadcast(
            "source.degraded",
            {
                "source_id": source_id,
                "reason": reason,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
