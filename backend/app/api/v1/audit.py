from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.domains.audit.service import audit_service

router = APIRouter(prefix="/audit", tags=["Audit System"])


@router.get("/logs")
async def list_audit_logs(
    action: str | None = Query(None, description="Filter by action name"),
    target_entity: str | None = Query(None, description="Filter by entity type"),
    actor_id: str | None = Query(None, description="Filter by actor ID"),
    trace_id: str | None = Query(None, description="Filter by trace ID"),
    limit: int = Query(50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Returns immutable append-only audit trail with cryptographic SHA-256 before/after hashes.
    Restricted to authorized DISASTER_MANAGER and SUPER_ADMIN roles.
    """
    if current_user.role not in ["DISASTER_MANAGER", "SUPER_ADMIN"]:
        raise ForbiddenError(
            "Audit log inspection is restricted to authorized managers and administrators."
        )

    return await audit_service.list_audit_logs(
        db=db,
        action=action,
        target_entity=target_entity,
        actor_id=actor_id,
        trace_id=trace_id,
        limit=limit,
    )
