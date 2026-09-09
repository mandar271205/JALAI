from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, status

from app.core.security import AuthenticatedUser, get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])

_tokens_db: dict[str, dict[str, Any]] = {}


@router.post("/device-token", status_code=status.HTTP_201_CREATED)
async def register_device_token(
    payload: dict[str, Any], current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    token = payload.get("expo_push_token")
    device_os = payload.get("device_os", "android")

    record = {
        "user_id": current_user.user_id,
        "expo_push_token": token,
        "device_os": device_os,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _tokens_db[token] = record
    return {"status": "REGISTERED", "token": token}
