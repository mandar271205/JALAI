import pytest
from httpx import AsyncClient

from app.domains.routing.engine import LowerRiskRoutingEngine


def test_routing_engine_edge_penalties_and_closure():
    engine = LowerRiskRoutingEngine()

    # Closed road has infinite weight
    closed_weight = engine.compute_edge_weight(base_distance=1000.0, depth_m=0.0, is_closed=True)
    assert closed_weight == float("inf")

    # Dry road vs flooded road
    dry_weight = engine.compute_edge_weight(base_distance=1000.0, depth_m=0.0, is_closed=False)
    flooded_weight = engine.compute_edge_weight(base_distance=1000.0, depth_m=0.8, is_closed=False)
    assert flooded_weight > dry_weight * 5.0


@pytest.mark.asyncio
async def test_routes_api_disclaimer_and_avoidance(client: AsyncClient):
    res = await client.post(
        "/api/v1/routes/lower-risk",
        json={
            "origin": {"latitude": 19.0712, "longitude": 72.8756},
            "destination": {"latitude": 19.0365, "longitude": 72.8601},
            "risk_aversion": 1.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "FeatureCollection"
    props = data["features"][0]["properties"]

    # Critical requirement: Never label route guaranteed safe
    assert "safety_disclaimer" in props
    assert "NOT guaranteed safe" in props["safety_disclaimer"]
    assert props["avoided_risky_segments_count"] > 0
    assert len(props["avoided_risky_segments"]) > 0
