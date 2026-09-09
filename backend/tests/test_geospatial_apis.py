import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_weather_etag_and_304_semantics(client: AsyncClient):
    # Initial request receives ETag
    res1 = await client.get("/api/v1/weather/current")
    assert res1.status_code == 200
    etag = res1.headers.get("ETag")
    assert etag is not None

    # Subsequent request with If-None-Match yields 304 Not Modified
    res2 = await client.get("/api/v1/weather/current", headers={"If-None-Match": etag})
    assert res2.status_code == 304


@pytest.mark.asyncio
async def test_risk_cells_spatial_and_canonical_fields(client: AsyncClient):
    res = await client.get("/api/v1/risk/cells?bbox=72.80,18.90,72.95,19.15&limit=10&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "items" in data
    assert "valid_time" in data
    assert "model_version" in data
    assert "data_version" in data
    assert "confidence" in data
    assert len(data["items"]) > 0

    # Verify H3 cell fields
    cell = data["items"][0]
    assert "h3_cell_id" in cell
    assert "risk_level" in cell


@pytest.mark.asyncio
async def test_risk_cell_timeline(client: AsyncClient):
    res = await client.get("/api/v1/risk/8860145b53fffff/timeline")
    assert res.status_code == 200
    data = res.json()
    assert data["h3_cell_id"] == "8860145b53fffff"
    assert len(data["timeline"]) == 4
    assert "probability" in data["timeline"][0]


@pytest.mark.asyncio
async def test_critical_assets_api(client: AsyncClient):
    res = await client.get("/api/v1/assets?limit=5")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert len(data["items"]) > 0
    assert "flood_threshold_m" in data["items"][0]
