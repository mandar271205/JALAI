import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_weather_sources_status(client: AsyncClient):
    response = await client.get("/api/v1/weather/sources/status")
    assert response.status_code == 200
    sources = response.json()
    assert isinstance(sources, list)
    assert len(sources) > 0
    assert "source_id" in sources[0]


@pytest.mark.asyncio
async def test_models_status(client: AsyncClient):
    response = await client.get("/api/v1/models/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert "models" in data


@pytest.mark.asyncio
async def test_nowcast_and_inundation_manifests(client: AsyncClient):
    nowcast_res = await client.get("/api/v1/nowcast/manifest")
    assert nowcast_res.status_code == 200
    assert "manifest_id" in nowcast_res.json()

    inundation_res = await client.get("/api/v1/inundation/manifest")
    assert inundation_res.status_code == 200
    assert "depth_cog_url" in inundation_res.json()


@pytest.mark.asyncio
async def test_risk_cells(client: AsyncClient):
    res = await client.get("/api/v1/risk/cells")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) > 0
    assert "model_version" in data
    assert "data_version" in data
    assert "confidence" in data


@pytest.mark.asyncio
async def test_routes_lower_risk(client: AsyncClient):
    res = await client.post(
        "/api/v1/routes/lower-risk",
        json={
            "origin": {"latitude": 19.05, "longitude": 72.85},
            "destination": {"latitude": 19.07, "longitude": 72.87},
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "FeatureCollection"


@pytest.mark.asyncio
async def test_openapi_json_generation(client: AsyncClient):
    res = await client.get("/openapi.json")
    assert res.status_code == 200
    schema = res.json()
    assert schema["info"]["title"] == "JalRakshak AI - Backend API"
    assert "/health" in schema["paths"]
    assert "/api/v1/weather/sources/status" in schema["paths"]
