import math
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.errors import ValidationError
from app.realtime.connection_manager import live_manager


class ReportVerificationPolicy:
    @staticmethod
    def classify_verification(ml_result: dict[str, Any]) -> str:
        """
        Backend verification decision policy based on ML vision confidence.
        """
        is_flood = ml_result.get("is_flood_related", True)
        confidence = ml_result.get("ai_confidence") or ml_result.get("confidence", 0.0)

        if not is_flood:
            return "REJECTED"
        if confidence >= 0.85:
            return "AI_VERIFIED"
        elif confidence >= 0.60:
            return "LIKELY"
        else:
            return "HUMAN_REVIEW"

    @staticmethod
    def correlate_nearby_incident(
        report_lat: float,
        report_lon: float,
        incidents: list[dict[str, Any]],
        threshold_meters: float = 500.0,
    ) -> str | None:
        """
        Correlates report to the nearest active incident within threshold meters using Haversine formula.
        """

        def haversine_distance(lat1, lon1, lat2, lon2):
            R = 6371000  # meters
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlambda = math.radians(lon2 - lon1)
            a = (
                math.sin(dphi / 2) ** 2
                + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
            )
            return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        closest_id = None
        min_dist = threshold_meters

        for inc in incidents:
            if inc.get("status") in ["RESOLVED", "CLOSED", "DISMISSED"]:
                continue
            lat = inc.get("latitude") or inc.get("location", {}).get("latitude")
            lon = inc.get("longitude") or inc.get("location", {}).get("longitude")
            if lat and lon:
                dist = haversine_distance(report_lat, report_lon, lat, lon)
                if dist <= min_dist:
                    min_dist = dist
                    closest_id = inc.get("incident_id")

        return closest_id

    @staticmethod
    async def apply_human_override(
        report: dict[str, Any],
        new_status: str,
        reason: str,
        officer_id: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        if not reason or not reason.strip():
            raise ValidationError("Human review override requires a mandatory non-empty reason.")

        valid_statuses = ["AI_VERIFIED", "HUMAN_VERIFIED", "REJECTED", "LIKELY"]
        if new_status.upper() not in valid_statuses:
            raise ValidationError(f"Invalid status '{new_status}'. Allowed: {valid_statuses}")

        prev_status = report.get("verification_status")
        report["verification_status"] = new_status.upper()
        report["verified_by"] = officer_id
        report["override_reason"] = reason

        # Audit event
        audit_event = {
            "log_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor_id": officer_id,
            "action": "FIELD_REPORT_HUMAN_OVERRIDE",
            "target_entity": "field_reports",
            "target_id": report["report_id"],
            "changes_json": {
                "previous_status": prev_status,
                "new_status": new_status.upper(),
                "reason": reason,
                "notes": notes,
            },
        }

        # Emit live domain event
        await live_manager.broadcast(
            "report.verified",
            {
                "report_id": report["report_id"],
                "previous_status": prev_status,
                "status": new_status.upper(),
                "override_by": officer_id,
                "reason": reason,
            },
        )

        return {"report": report, "audit_event": audit_event}
