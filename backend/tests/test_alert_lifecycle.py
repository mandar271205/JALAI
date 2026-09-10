import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_alert_lifecycle_draft_approve_publish_rbac(client: AsyncClient):
    # 1. ANALYST drafts alert
    analyst_headers = {"X-Mock-Role": "ANALYST", "X-Mock-User": "usr-analyst-01"}
    draft_res = await client.post(
        "/api/v1/alerts/draft",
        json={
            "headline": "Flash Flood Warning - Kurla",
            "description": "Heavy rainfall runoff accumulation",
            "severity": "Extreme",
            "urgency": "Immediate",
            "certainty": "Observed",
            "ward_id": "WARD-08-KURLA",
            "area_description": "Kurla West",
        },
        headers=analyst_headers,
    )
    assert draft_res.status_code == 201
    draft = draft_res.json()
    alert_id = draft["alert_id"]
    assert draft["status"] == "DRAFT"

    # 2. CITIZEN forbidden from approving
    citizen_headers = {"X-Mock-Role": "CITIZEN", "X-Mock-User": "usr-citizen-01"}
    cit_res = await client.post(f"/api/v1/alerts/{alert_id}/approve", headers=citizen_headers)
    assert cit_res.status_code == 403

    # 3. Two-Person Rule: Same actor (usr-analyst-01) forbidden from approving own alert even with APPROVER role
    self_approve_headers = {"X-Mock-Role": "ALERT_APPROVER", "X-Mock-User": "usr-analyst-01"}
    self_res = await client.post(f"/api/v1/alerts/{alert_id}/approve", headers=self_approve_headers)
    assert self_res.status_code == 403
    err_body = self_res.json()
    err_msg = err_body.get("error", {}).get("message", "") or err_body.get("detail", "")
    assert "Two-person authorization violation" in err_msg

    # 4. Distinct ALERT_APPROVER approves
    approver_headers = {"X-Mock-Role": "ALERT_APPROVER", "X-Mock-User": "usr-approver-01"}
    appr_res = await client.post(f"/api/v1/alerts/{alert_id}/approve", headers=approver_headers)
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "APPROVED"
    assert appr_res.json()["audit_event"]["action"] == "ALERT_APPROVED"

    # 4. ALERT_APPROVER publishes
    pub_res = await client.post(f"/api/v1/alerts/{alert_id}/publish", headers=approver_headers)
    assert pub_res.status_code == 200
    assert pub_res.json()["status"] == "PUBLISHED"

    # 5. Fetch CAP XML
    xml_res = await client.get(f"/api/v1/alerts/{alert_id}/cap.xml")
    assert xml_res.status_code == 200
    assert xml_res.headers["content-type"] == "application/xml"
    assert "urn:oasis:names:tc:emergency:cap:1.2" in xml_res.text
