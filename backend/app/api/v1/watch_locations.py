from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import AuthenticatedUser, get_current_user
from app.domains.watch_locations.service import watch_service

router = APIRouter(prefix="/watch-locations", tags=["Watch Locations"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_watch_location(
    payload: dict[str, Any], current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    return watch_service.create_location(
        user_id=current_user.user_id,
        label=payload.get("label", "Home"),
        latitude=float(payload.get("latitude", 19.05)),
        longitude=float(payload.get("longitude", 72.85)),
        h3_cell_id=payload.get("h3_cell_id"),
        ward_id=payload.get("ward_id"),
        risk_threshold=payload.get("risk_threshold", "HIGH"),
        notify_push=payload.get("notify_push", True),
    )


@router.get("")
async def list_watch_locations(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    locations = watch_service.list_locations(current_user.user_id)

    # Seed demo locations if first time
    if not locations:
        watch_service.create_location(
            user_id=current_user.user_id,
            label="Parents' Home (Kurla West)",
            latitude=19.0685,
            longitude=72.8720,
            h3_cell_id="8860145b53fffff",
            ward_id="WARD-08-KURLA",
            risk_threshold="HIGH",
            notify_push=True,
        )
        watch_service.create_location(
            user_id=current_user.user_id,
            label="Workplace (BKC G-Block)",
            latitude=19.0665,
            longitude=72.8680,
            h3_cell_id="8860145b51fffff",
            ward_id="WARD-12-DHARAVI",
            risk_threshold="SEVERE",
            notify_push=True,
        )
        locations = watch_service.list_locations(current_user.user_id)

    # Evaluate live risk intersection against H3 cells
    from app.integrations.ml.provider import get_ml_provider

    ml = get_ml_provider()
    risk_data = await ml.get_risk_cells()
    risk_cells = risk_data if isinstance(risk_data, list) else risk_data.get("items", [])

    enriched = []
    for loc in locations:
        intersection = watch_service.check_risk_intersection(loc, risk_cells)
        enriched.append({
            **loc,
            "risk_status": intersection.get("actual_risk", "NORMAL") if intersection else "NORMAL",
            "flood_depth_m": intersection.get("flood_depth_m", 0.0) if intersection else 0.0,
            "is_alert_active": bool(intersection and intersection.get("triggered")),
        })
    return enriched


@router.delete("/{location_id}")
async def remove_watch_location(
    location_id: str, current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, str]:
    deleted = watch_service.delete_location(location_id, current_user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Watch location not found.")
    return {"status": "DELETED", "location_id": location_id}
