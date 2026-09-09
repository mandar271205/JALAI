import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_raster_tilejson_and_tile(client: AsyncClient):
    # TileJSON
    res_json = await client.get("/api/v1/tiles/raster/nowcast/tilejson.json")
    assert res_json.status_code == 200
    data = res_json.json()
    assert data["tilejson"] == "3.0.0"
    assert len(data["tiles"]) > 0

    # Raster PNG tile with live caching header (60s)
    res_tile = await client.get("/api/v1/tiles/raster/nowcast/10/583/430.png")
    assert res_tile.status_code == 200
    assert res_tile.headers["content-type"] == "image/png"
    assert "max-age=60" in res_tile.headers["Cache-Control"]

    # Replay tile with immutable long caching header
    res_replay = await client.get(
        "/api/v1/tiles/raster/historical_20250726/10/583/430.png?immutable=true"
    )
    assert res_replay.status_code == 200
    assert "immutable" in res_replay.headers["Cache-Control"]


@pytest.mark.asyncio
async def test_vector_tilejson_and_mvt(client: AsyncClient):
    # Vector TileJSON
    res_json = await client.get("/api/v1/tiles/vector/risk_cells/tilejson.json")
    assert res_json.status_code == 200
    data = res_json.json()
    assert data["tilejson"] == "3.0.0"
    assert data["vector_layers"][0]["id"] == "risk_cells"

    # MVT Protobuf vector tile
    res_mvt = await client.get("/api/v1/tiles/vector/risk_cells/12/2334/1720.pbf")
    assert res_mvt.status_code == 200
    assert res_mvt.headers["content-type"] == "application/x-protobuf"
    assert len(res_mvt.content) > 0
