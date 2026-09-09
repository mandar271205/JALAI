import pytest
from httpx import AsyncClient

from app.core.errors import AppException
from app.domains.responders.service import responder_service


def test_responder_task_lifecycle_and_optimistic_locking():
    # 1. Create task (initial version = 1)
    task = responder_service.create_task(
        incident_id="inc-100", responder_id="resp-01", task_type="VERIFY_LOCATION"
    )
    task_id = task["task_id"]
    assert task["version"] == 1
    assert task["status"] == "ASSIGNED"

    # 2. Action: MEASURE_DEPTH with correct base_version (1) -> increments version to 2
    updated1 = responder_service.apply_action(
        task_id=task_id,
        action="MEASURE_DEPTH",
        expected_version=1,
        actor_id="resp-01",
        measured_depth_cm=65.0,
    )
    assert updated1["version"] == 2
    assert updated1["measured_depth_cm"] == 65.0
    assert updated1["status"] == "ON_SCENE"

    # 3. Optimistic locking failure: attempting mutation with stale base_version (1)
    with pytest.raises(AppException) as exc:
        responder_service.apply_action(
            task_id=task_id,
            action="ROAD_BLOCKED",
            expected_version=1,  # Stale! Current version is 2
            actor_id="resp-02",
        )
    assert exc.value.status_code == 409
    assert exc.value.code == "VERSION_CONFLICT"

    # 4. Completing task with valid version (2) -> increments version to 3 and status COMPLETED
    updated2 = responder_service.apply_action(
        task_id=task_id, action="COMPLETE_TASK", expected_version=2, actor_id="resp-01"
    )
    assert updated2["version"] == 3
    assert updated2["status"] == "COMPLETED"
    assert updated2["completed_at"] is not None


@pytest.mark.asyncio
async def test_responder_tasks_api(client: AsyncClient):
    headers = {"X-Mock-Role": "ADMIN", "X-Mock-User": "usr-admin-01"}

    # Create task via API
    create_res = await client.post(
        "/api/v1/responders/tasks",
        json={
            "incident_id": "inc-api-01",
            "responder_id": "resp-field-44",
            "task_type": "ROAD_BLOCKED",
            "instructions": "Place barricades on submerged subway",
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    task_id = create_res.json()["task_id"]

    # Action via API
    action_res = await client.post(
        f"/api/v1/responders/tasks/{task_id}/action",
        json={"action": "COMPLETE_TASK", "base_version": 1, "notes": "Subway fully barricaded"},
        headers={"X-Mock-Role": "FIELD_RESPONDER", "X-Mock-User": "resp-field-44"},
    )
    assert action_res.status_code == 200
    assert action_res.json()["status"] == "COMPLETED"
    assert action_res.json()["version"] == 2
