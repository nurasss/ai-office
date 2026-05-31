"""API and Telegram access-control helpers."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status

from core.config import get_settings


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return token.strip()


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    """Optionally require AI_OFFICE_API_KEY for public API deployments."""
    settings = get_settings()
    if not settings.ai_office_require_api_key:
        request.state.api_authenticated = True
        request.state.api_auth_mode = "disabled"
        return

    expected = settings.ai_office_api_key.strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI_OFFICE_API_KEY is not configured.",
        )

    provided = (x_api_key or "").strip() or _extract_bearer_token(authorization)
    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )

    request.state.api_authenticated = True
    request.state.api_auth_mode = "api_key"


def parse_id_allowlist(raw_value: str) -> set[str]:
    """Parse comma-separated Telegram ids into strings."""
    return {item.strip() for item in raw_value.split(",") if item.strip()}


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {
        "task:create",
        "task:read",
        "task:cancel",
        "approval:read",
        "approval:decide",
        "audit:read",
        "knowledge:upload",
        "knowledge:read",
        "integration:manage",
        "cost:read",
    },
    "admin": {
        "task:create",
        "task:read",
        "task:cancel",
        "approval:read",
        "approval:decide",
        "audit:read",
        "knowledge:upload",
        "knowledge:read",
        "cost:read",
    },
    "manager": {"task:create", "task:read", "approval:read", "approval:decide", "audit:read", "cost:read"},
    "operator": {"task:create", "task:read", "approval:read", "knowledge:read"},
    "viewer": {"task:read", "approval:read", "audit:read", "knowledge:read", "cost:read"},
    "agent_service": {"task:create", "task:read", "knowledge:read"},
}


async def get_current_user(
    request: Request,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
) -> dict[str, str]:
    """Return a dev-safe user identity from headers.

    In local development, missing headers resolve to an owner user so the app
    remains easy to run. Tests can pass `X-User-Role: viewer` to verify denial.
    """
    role = (x_user_role or "owner").strip().lower()
    if role not in ROLE_PERMISSIONS:
        role = "viewer"
    user = {"id": (x_user_id or "dev-user").strip(), "role": role}
    request.state.current_user = user
    return user


def require_permission(permission: str) -> Callable:
    async def dependency(user: dict[str, str] = Depends(get_current_user)) -> None:
        role = user.get("role", "viewer")
        if permission not in ROLE_PERMISSIONS.get(role, set()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission}",
            )

    return dependency
