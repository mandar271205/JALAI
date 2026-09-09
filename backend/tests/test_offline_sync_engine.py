import pytest
from httpx import AsyncClient

from app.domains.responders.service import responder_service


@pytest.mark.asyncio
async def test_offline_batch_sync_idempotency_and_conflicts(client: AsyncClient):
    # Setup test responder task (version 1)
    task = responder_service.create_task(
        incident_id="inc-sync-01", responder_id="resp-sync-01", task_type="VERIFY_LOCATION"
    )
    task_id = task["task_id"]

    # 1. Successful batch mutation
    batch_payload_1 = {
        "client_id": "mobile-client-01",
        "sync_version": 1,
        "client_timestamp": "2026-09-08T15:30:00Z",
        "mutations": [
            {
                "mutation_id": "mut-sync-101",
                "entity_type": "RESPONDER_TASK",
                "action": "MEASURE_DEPTH",
                "entity_id": task_id,
                "base_version": 1,
                "data": {"depth_cm": 48.0},
            }
        ],
    }
    res1 = await client.post("/api/v1/sync/batch", json=batch_payload_1)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["results"][0]["status"] == "accepted"
    assert data1["results"][0]["new_version"] == 2

    # 2. Duplicate mutation replay: must return duplicate status without re-executing
    res2 = await client.post("/api/v1/sync/batch", json=batch_payload_1)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["results"][0]["status"] == "duplicate"

    # 3. Conflict detection (needs_merge): client mutation based on stale version 1 when server is at version 2
    batch_payload_conflict = {
        "client_id": "mobile-client-02",
        "sync_version": 1,
        "client_timestamp": "2026-09-08T15:31:00Z",
        "mutations": [
            {
                "mutation_id": "mut-sync-102",
                "entity_type": "RESPONDER_TASK",
                "action": "ROAD_BLOCKED",
                "entity_id": task_id,
                "base_version": 1,  # Conflict! Server is at version 2
                "data": {},
            }
        ],
    }
    res3 = await client.post("/api/v1/sync/batch", json=batch_payload_conflict)
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["results"][0]["status"] == "needs_merge"
    assert data3["results"][0]["server_version"] == 2
