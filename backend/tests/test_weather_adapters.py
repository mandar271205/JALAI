import pytest

from app.domains.weather.adapters.demo_adapter import FileSystemDemoAdapter
from app.domains.weather.adapters.ingestion_pipeline import WeatherIngestionPipeline


@pytest.mark.asyncio
async def test_demo_weather_adapter_replay():
    adapter = FileSystemDemoAdapter(source_id="demo-radar", source_type="RADAR")
    assert adapter.source_id == "demo-radar"
    assert adapter.source_type == "RADAR"

    # 1. Health check
    health = await adapter.health_check()
    assert health["status"] == "HEALTHY"

    # 2. List available items
    items = await adapter.list_available()
    assert len(items) > 0
    item_id = items[0]["item_id"]

    # 3. Fetch & metadata parse
    data = await adapter.fetch(item_id)
    assert len(data) > 0
    meta = await adapter.parse_metadata(data)
    assert "sha256" in meta
    assert meta["crs"] == "EPSG:4326"

    # 4. Normalize
    norm = await adapter.normalize(data)
    assert norm["canonical_unit"] == "mm/h"
    assert norm["max_rate_mm_h"] > 0


@pytest.mark.asyncio
async def test_weather_ingestion_pipeline_with_degraded_source():
    # Adapter that fails health check
    class FailingAdapter(FileSystemDemoAdapter):
        async def health_check(self):
            return {"status": "OFFLINE", "reason": "Telemetry station unreachable"}

    healthy = FileSystemDemoAdapter(source_id="healthy-radar")
    failing = FailingAdapter(source_id="failing-station")

    pipeline = WeatherIngestionPipeline(adapters=[healthy, failing])
    result = await pipeline.run_ingestion_cycle()

    # Healthy source should be ingested, failing source marked degraded without crashing
    assert result["ingested_count"] == 1
    assert "failing-station" in result["degraded_sources"]
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["source_id"] == "healthy-radar"
    assert result["artifacts"][0]["is_immutable"] is True
