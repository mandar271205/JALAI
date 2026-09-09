import pytest
from httpx import AsyncClient

from app.domains.watch_locations.service import watch_service


@pytest.mark.asyncio
async def test_watch_locations_api_and_risk_trigger(client: AsyncClient):
    headers = {"X-Mock-Role": "CITIZEN", "X-Mock-User": "usr-citizen-99"}

    # 1. Create watch location
    create_res = await client.post(
        "/api/v1/watch-locations",
        json={
            "label": "Family Residence",
            "latitude": 19.04,
            "longitude": 72.86,
            "h3_cell_id": "8860145b53fffff",
            "risk_threshold": "HIGH",
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    loc = create_res.json()
    loc_id = loc["location_id"]
    assert loc["label"] == "Family Residence"

    # 2. List watch locations
    list_res = await client.get("/api/v1/watch-locations", headers=headers)
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) >= 1

    # 3. Evaluate risk intersection logic
    risk_cells = [
        {"h3_cell_id": "8860145b53fffff", "risk_level": "SEVERE", "flood_depth_m": 0.82},
        {"h3_cell_id": "8860145b51fffff", "risk_level": "LOW", "flood_depth_m": 0.05},
    ]
    trigger = watch_service.check_risk_intersection(loc, risk_cells)
    assert trigger is not None
    assert trigger["triggered"] is True
    assert trigger["actual_risk"] == "SEVERE"

    # 4. Delete watch location
    del_res = await client.delete(f"/api/v1/watch-locations/{loc_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "DELETED"
