"""API and Telegram access-control helpers."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

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
    """Require AI_OFFICE_API_KEY via X-API-Key or Authorization: Bearer."""
    expected = get_settings().ai_office_api_key.strip()
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


def parse_id_allowlist(raw_value: str) -> set[str]:
    """Parse comma-separated Telegram ids into strings."""
    return {item.strip() for item in raw_value.split(",") if item.strip()}

