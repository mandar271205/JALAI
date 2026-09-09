import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_field_report_direct_signed_upload_flow(client: AsyncClient):
    # Step 1: Create draft report
    draft_res = await client.post(
        "/api/v1/reports/draft",
        json={
            "latitude": 19.0712,
            "longitude": 72.8756,
            "description": "Submerged road near Kurla west depot",
        },
    )
    assert draft_res.status_code == 201
    draft_data = draft_res.json()
    report_id = draft_data["report_id"]
    assert draft_data["verification_status"] == "DRAFT"

    # Step 2: Request signed upload intent
    intent_res = await client.post(
        "/api/v1/reports/upload-intent",
        json={
            "report_id": report_id,
            "filename": "waterlogging_photo.jpg",
            "content_type": "image/jpeg",
            "file_size_bytes": 2048500,
        },
    )
    assert intent_res.status_code == 201
    intent_data = intent_res.json()
    assert "upload_id" in intent_data
    assert "presigned_url" in intent_data
    assert intent_data["status"] == "PENDING"
    upload_id = intent_data["upload_id"]

    # Step 3: Finalize upload (simulates client completed direct binary upload to S3)
    finalize_res = await client.post(
        "/api/v1/reports/upload-finalize",
        json={
            "upload_id": upload_id,
            "sha256_checksum": "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
        },
    )
    assert finalize_res.status_code == 200
    final_data = finalize_res.json()
    assert final_data["status"] == "FINALIZED"
    assert "image_url" in final_data
    assert final_data["verification_job"]["status"] == "QUEUED"
    assert final_data["verification_job"]["preliminary_result"]["is_flood_related"] is True
