"""Device push token registration and management for mobile push notifications."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import AuthenticatedUser, get_current_user

router = APIRouter(prefix="/devices", tags=["Device Push Tokens"])

_device_tokens: dict[str, dict[str, Any]] = {}


@router.post("/push-token", status_code=status.HTTP_201_CREATED)
async def register_push_token(
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Register or refresh an Expo or FCM push notification token."""
    token = payload.get("token") or payload.get("expo_push_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Token string ('token' or 'expo_push_token') is required.",
        )
    device_os = payload.get("device_os", "android")
    device_id = payload.get("device_id") or token

    record = {
        "device_id": device_id,
        "token": token,
        "user_id": current_user.user_id,
        "device_os": device_os,
        "registered_at": datetime.now(UTC).isoformat(),
    }
    _device_tokens[device_id] = record
    return {
        "status": "REGISTERED",
        "device_id": device_id,
        "token": token,
    }


@router.delete("/push-token/{device_id}", status_code=status.HTTP_200_OK)
async def delete_push_token(
    device_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Unregister a push notification token upon user logout."""
    if device_id in _device_tokens:
        del _device_tokens[device_id]
        return {"status": "UNREGISTERED", "device_id": device_id}

    # Also check if token value was passed as device_id
    for k, v in list(_device_tokens.items()):
        if v.get("token") == device_id and v.get("user_id") == current_user.user_id:
            del _device_tokens[k]
            return {"status": "UNREGISTERED", "device_id": k}

    return {"status": "UNREGISTERED", "device_id": device_id}
