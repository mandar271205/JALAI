from typing import Any

from fastapi import APIRouter, Depends

from app.core.security import AuthenticatedUser, get_current_user
from app.domains.sync.service import sync_engine

router = APIRouter(prefix="/sync", tags=["Offline Synchronization"])


@router.post("/batch")
async def process_batch_sync(
    payload: dict[str, Any], current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    client_id = payload.get("client_id") or current_user.user_id
    sync_version = int(payload.get("sync_version", 1))
    client_timestamp = payload.get("client_timestamp", "")
    mutations = payload.get("mutations", [])

    return sync_engine.process_batch_sync(
        client_id=client_id,
        sync_version=sync_version,
        client_timestamp=client_timestamp,
        mutations=mutations,
    )
