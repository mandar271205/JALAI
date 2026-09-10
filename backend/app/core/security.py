from enum import StrEnum
from typing import Any

import jwt
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError


class UserRole(StrEnum):
    CITIZEN = "CITIZEN"
    FIELD_RESPONDER = "FIELD_RESPONDER"
    ANALYST = "ANALYST"
    ALERT_APPROVER = "ALERT_APPROVER"
    MUNICIPAL_OFFICER = "MUNICIPAL_OFFICER"
    DISASTER_MANAGER = "DISASTER_MANAGER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"
    ML_ADMIN = "ML_ADMIN"


class AuthenticatedUser(BaseModel):
    user_id: str
    email: str | None = None
    role: UserRole
    metadata: dict[str, Any] = {}


http_bearer = HTTPBearer(auto_error=False)


def parse_user_role(raw_role: str | None) -> UserRole:
    if not raw_role:
        return UserRole.CITIZEN
    try:
        return UserRole(raw_role.upper())
    except ValueError:
        return UserRole.CITIZEN


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    x_mock_user: str | None = Header(None, alias="X-Mock-User"),
    x_mock_role: str | None = Header(None, alias="X-Mock-Role"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    """
    Decodes and validates authentication credentials.
    In local dev / mock mode, allows Header or default mock identity.
    In production / Supabase mode, verifies the signed JWT token.
    """
    if credentials and credentials.credentials:
        token = credentials.credentials
        try:
            # Verify signed JWT token
            payload = jwt.decode(
                token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated"
            )
            user_id = payload.get("sub", "usr-sub-001")
            email = payload.get("email")

            app_meta = payload.get("app_metadata", {})
            user_meta = payload.get("user_metadata", {})
            raw_role = app_meta.get("role") or user_meta.get("role") or payload.get("role")
            role = parse_user_role(raw_role)

            return AuthenticatedUser(
                user_id=user_id, email=email, role=role, metadata={**app_meta, **user_meta}
            )
        except jwt.PyJWTError as e:
            raise UnauthorizedError(f"Invalid authentication token: {str(e)}")

    if settings.AUTH_MODE == "mock":
        user_id = x_mock_user or x_user_id or "usr-dev-admin-001"
        effective_role = x_mock_role or x_user_role or "ADMIN"
        role_enum = parse_user_role(effective_role)
        return AuthenticatedUser(
            user_id=user_id,
            email=f"{user_id}@jalrakshak.local",
            role=role_enum,
            metadata={"auth_provider": "local_mock"},
        )

    raise UnauthorizedError("Missing bearer authentication token")


def require_roles(allowed_roles: list[UserRole]):
    """
    RBAC dependency ensuring the authenticated user possesses one of the authorized roles.
    Enforced strictly server-side.
    """

    async def role_checker(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if user.role not in allowed_roles:
            raise ForbiddenError(
                f"Role '{user.role.value}' is not authorized to access this resource. Allowed: {[r.value for r in allowed_roles]}"
            )
        return user

    return role_checker
