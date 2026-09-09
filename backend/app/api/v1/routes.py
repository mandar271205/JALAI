from typing import Any

from fastapi import APIRouter

from app.domains.routing.engine import routing_engine

router = APIRouter(prefix="/routes", tags=["Routes"])


@router.post("/lower-risk")
async def compute_lower_risk_route(payload: dict[str, Any]) -> dict[str, Any]:
    origin = payload.get("origin", {"latitude": 19.0712, "longitude": 72.8756})
    destination = payload.get("destination", {"latitude": 19.0365, "longitude": 72.8601})
    aversion = float(payload.get("risk_aversion", 1.0))
    return routing_engine.find_lower_risk_route(
        origin_lat=origin.get("latitude", 19.0712),
        origin_lon=origin.get("longitude", 72.8756),
        dest_lat=destination.get("latitude", 19.0365),
        dest_lon=destination.get("longitude", 72.8601),
        risk_aversion=aversion,
    )
