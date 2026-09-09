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
    return watch_service.list_locations(current_user.user_id)


@router.delete("/{location_id}")
async def remove_watch_location(
    location_id: str, current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, str]:
    deleted = watch_service.delete_location(location_id, current_user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Watch location not found.")
    return {"status": "DELETED", "location_id": location_id}
