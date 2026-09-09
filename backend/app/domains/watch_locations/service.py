import uuid
from datetime import UTC, datetime
from typing import Any

RISK_SEVERITY_ORDER = {"LOW": 1, "MODERATE": 2, "HIGH": 3, "SEVERE": 4, "CRITICAL": 4}


class WatchLocationService:
    def __init__(self):
        self._locations: dict[str, dict[str, Any]] = {}

    def create_location(
        self,
        user_id: str,
        label: str,
        latitude: float,
        longitude: float,
        h3_cell_id: str | None = None,
        ward_id: str | None = None,
        risk_threshold: str = "HIGH",
        notify_push: bool = True,
    ) -> dict[str, Any]:
        location_id = str(uuid.uuid4())
        # Default mock H3 cell resolution if not provided
        cell_id = h3_cell_id or "8860145b53fffff"

        record = {
            "location_id": location_id,
            "user_id": user_id,
            "label": label,
            "latitude": latitude,
            "longitude": longitude,
            "h3_cell_id": cell_id,
            "ward_id": ward_id,
            "risk_threshold": risk_threshold.upper(),
            "notify_push": notify_push,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._locations[location_id] = record
        return record

    def list_locations(self, user_id: str) -> list[dict[str, Any]]:
        return [loc for loc in self._locations.values() if loc["user_id"] == user_id]

    def delete_location(self, location_id: str, user_id: str) -> bool:
        if location_id in self._locations and self._locations[location_id]["user_id"] == user_id:
            del self._locations[location_id]
            return True
        return False

    def check_risk_intersection(
        self, location: dict[str, Any], risk_cells: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """
        Evaluates whether an active risk cell exceeds the watch location's risk threshold.
        """
        threshold_rank = RISK_SEVERITY_ORDER.get(location["risk_threshold"], 3)
        loc_h3 = location.get("h3_cell_id")

        for cell in risk_cells:
            if cell.get("h3_cell_id") == loc_h3:
                cell_rank = RISK_SEVERITY_ORDER.get(cell.get("risk_level", "LOW"), 1)
                if cell_rank >= threshold_rank:
                    return {
                        "triggered": True,
                        "location_label": location["label"],
                        "threshold": location["risk_threshold"],
                        "actual_risk": cell.get("risk_level"),
                        "flood_depth_m": cell.get("flood_depth_m", 0.0),
                        "h3_cell_id": loc_h3,
                    }
        return None


watch_service = WatchLocationService()
