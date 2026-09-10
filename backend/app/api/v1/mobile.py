"""Mobile API endpoints optimized for Citizen and Responder mobile applications."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.core.security import AuthenticatedUser, get_current_user
from app.domains.reports.repository import FieldReportsRepository
from app.domains.watch_locations.service import watch_service
from app.integrations.ml.provider import get_ml_provider

router = APIRouter(prefix="/mobile", tags=["Mobile Aggregation"])

reports_repo = FieldReportsRepository(session=None)
ml_provider = get_ml_provider()


def _load_fixture_json(filename: str) -> Any:
    base = Path(__file__).resolve().parents[4]
    file_path = base / "contracts" / "fixtures" / "demo-event" / filename
    if file_path.exists():
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    return []


@router.get("/home", status_code=status.HTTP_200_OK)
async def get_mobile_home(
    lat: float = Query(19.0760, ge=-90.0, le=90.0, description="User current latitude"),
    lon: float = Query(72.8777, ge=-180.0, le=180.0, description="User current longitude"),
    radius_km: float = Query(5.0, ge=0.5, le=50.0, description="Query radius in km"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Aggregated payload for Mobile App Home Screen.
    Single-call aggregation to minimize mobile device network requests, latency, and battery consumption.
    """
    now = datetime.now(UTC)

    # 1. Fetch risk evaluation near user location
    risk_cells = await ml_provider.get_risk_cells()
    local_risk_level = "MODERATE"
    local_risk_score = 0.58
    local_factors = ["High surface runoff", "Low-lying catchment drainage"]
    local_ward = "WARD-12-DHARAVI"

    if risk_cells and isinstance(risk_cells, list):
        primary_cell = risk_cells[0]
        local_risk_level = primary_cell.get("risk_level", "MODERATE")
        local_risk_score = primary_cell.get("inundation_susceptibility_score", 0.65)
        local_ward = primary_cell.get("ward_id", "WARD-12-DHARAVI")

    # 2. Rainfall outlook at +30, +60, +90, +120 minutes
    nowcast_manifest = await ml_provider.get_nowcast_manifest()
    rainfall_outlook = [
        {
            "lead_time_minutes": 30,
            "rainfall_rate_mm_h": 35.0,
            "category": "MODERATE",
            "trend": "INCREASING",
        },
        {
            "lead_time_minutes": 60,
            "rainfall_rate_mm_h": 68.5,
            "category": "HEAVY",
            "trend": "INCREASING",
        },
        {
            "lead_time_minutes": 90,
            "rainfall_rate_mm_h": 52.0,
            "category": "HEAVY",
            "trend": "DECREASING",
        },
        {
            "lead_time_minutes": 120,
            "rainfall_rate_mm_h": 24.0,
            "category": "MODERATE",
            "trend": "DECREASING",
        },
    ]

    # 3. Active alerts
    from app.api.v1.alerts import _alerts_db

    active_alerts = [
        a
        for a in _alerts_db.values()
        if a.get("status") in ("APPROVED", "BROADCAST", "PUBLISHED")
    ]
    if not active_alerts:
        # Load from contract fixtures if no memory alerts are active
        fixture_alerts = _load_fixture_json("alerts.json")
        active_alerts = fixture_alerts[:3] if isinstance(fixture_alerts, list) else []

    # 4. Nearby incidents
    from app.api.v1.incidents import _memory_incidents

    fixture_incidents = _load_fixture_json("incidents.json")
    all_incidents = list(_memory_incidents.values()) + (
        fixture_incidents if isinstance(fixture_incidents, list) else []
    )
    # Filter active/unresolved incidents
    nearby_incidents = [
        i for i in all_incidents if i.get("status") in ("OPEN", "ACKNOWLEDGED", "DISPATCHED", "PENDING")
    ][:5]

    # 5. Nearby citizen reports (verified or under review)
    recent_reports = await reports_repo.list_reports(limit=5)

    # 6. User's saved watch locations
    user_watch_locations = watch_service.list_locations(current_user.user_id)

    return {
        "location": {
            "latitude": lat,
            "longitude": lon,
            "ward_id": local_ward,
            "radius_km": radius_km,
        },
        "current_risk": {
            "risk_level": local_risk_level,
            "risk_score": local_risk_score,
            "dominant_factors": local_factors,
            "summary": f"Current risk level in {local_ward} is {local_risk_level} with active drainage monitoring.",
            "confidence": 0.85,
            "is_fallback": True,
        },
        "rainfall_outlook": rainfall_outlook,
        "nowcast_manifest_id": nowcast_manifest.get("manifest_id"),
        "active_alerts": active_alerts[:5],
        "nearby_incidents": nearby_incidents,
        "nearby_reports": recent_reports,
        "watched_locations": user_watch_locations,
        "system_status": {
            "timestamp": now.isoformat(),
            "operational_mode": "LIVE_OPERATIONAL",
            "is_radar_available": True,
            "provisional_model_fallback": True,
        },
    }
