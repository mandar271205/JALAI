import pytest

from app.core.errors import ValidationError
from app.domains.reports.policy import ReportVerificationPolicy


def test_report_verification_policy_tiers():
    # Tier 1: High confidence flood -> AI_VERIFIED
    t1 = ReportVerificationPolicy.classify_verification(
        {"is_flood_related": True, "confidence": 0.92}
    )
    assert t1 == "AI_VERIFIED"

    # Tier 2: Moderate confidence flood -> LIKELY
    t2 = ReportVerificationPolicy.classify_verification(
        {"is_flood_related": True, "confidence": 0.75}
    )
    assert t2 == "LIKELY"

    # Tier 3: Low confidence -> HUMAN_REVIEW
    t3 = ReportVerificationPolicy.classify_verification(
        {"is_flood_related": True, "confidence": 0.45}
    )
    assert t3 == "HUMAN_REVIEW"

    # Tier 4: Not flood related -> REJECTED
    t4 = ReportVerificationPolicy.classify_verification(
        {"is_flood_related": False, "confidence": 0.99}
    )
    assert t4 == "REJECTED"


def test_incident_correlation_within_threshold():
    incidents = [
        {"incident_id": "inc-near-01", "latitude": 19.0710, "longitude": 72.8750, "status": "OPEN"},
        {"incident_id": "inc-far-02", "latitude": 19.1500, "longitude": 72.9500, "status": "OPEN"},
    ]
    # Report 50 meters away
    near_id = ReportVerificationPolicy.correlate_nearby_incident(
        19.0712, 72.8752, incidents, threshold_meters=500.0
    )
    assert near_id == "inc-near-01"

    # Report 10 km away
    far_id = ReportVerificationPolicy.correlate_nearby_incident(
        18.9000, 72.8000, incidents, threshold_meters=500.0
    )
    assert far_id is None


@pytest.mark.asyncio
async def test_human_override_requires_reason():
    report = {"report_id": "rep-test-01", "verification_status": "HUMAN_REVIEW"}

    # Missing reason raises ValidationError
    with pytest.raises(ValidationError):
        await ReportVerificationPolicy.apply_human_override(
            report=report, new_status="HUMAN_VERIFIED", reason="", officer_id="usr-officer-01"
        )

    # Valid reason succeeds and emits audit event
    res = await ReportVerificationPolicy.apply_human_override(
        report=report,
        new_status="HUMAN_VERIFIED",
        reason="Verified via ground CCTV footage at Kurla depot",
        officer_id="usr-officer-01",
    )
    assert res["report"]["verification_status"] == "HUMAN_VERIFIED"
    assert res["audit_event"]["action"] == "FIELD_REPORT_HUMAN_OVERRIDE"
