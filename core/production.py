"""Production readiness checks for controlled pilot deployments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from core.config import Environment, Settings, get_settings
from core.db import get_engine


PLACEHOLDER_FRAGMENTS = (
    "change-me",
    "changeme",
    "example",
    "placeholder",
    "todo",
    "your-",
    "set-me",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _is_placeholder(value: str) -> bool:
    stripped = (value or "").strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    return any(fragment in lowered for fragment in PLACEHOLDER_FRAGMENTS)


def _is_local_url(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return (
        not lowered
        or "localhost" in lowered
        or "127.0.0.1" in lowered
        or lowered.startswith("http://0.0.0.0")
    )


def _provider_key_present(settings: Settings, provider: str) -> bool:
    provider = provider.strip().lower()
    if provider == "openai":
        return bool(settings.openai_api_key.strip())
    if provider == "anthropic":
        return bool(settings.anthropic_api_key.strip())
    if provider == "google":
        return bool(settings.google_api_key.strip())
    if provider == "deepseek":
        return bool(settings.deepseek_api_key.strip())
    if provider == "custom":
        return bool(settings.brain_api_key.strip())
    return False


def validate_production_settings(settings: Settings) -> list[str]:
    """Return production safety issues for the provided settings."""
    errors: list[str] = []
    if settings.environment != Environment.PRODUCTION:
        return errors

    if not settings.ai_office_require_api_key:
        errors.append("AI_OFFICE_REQUIRE_API_KEY must be true.")
    if _is_placeholder(settings.ai_office_api_key):
        errors.append("AI_OFFICE_API_KEY must be a non-placeholder secret.")
    if _is_placeholder(settings.ai_office_admin_token):
        errors.append("AI_OFFICE_ADMIN_TOKEN must be a non-placeholder secret.")
    if settings.database_url.strip().startswith("sqlite"):
        errors.append("DATABASE_URL must point to Postgres, not SQLite.")
    if not settings.database_url.strip().startswith(("postgresql", "postgres://")):
        errors.append("DATABASE_URL must use a Postgres scheme.")
    if not settings.redis_url.strip():
        errors.append("REDIS_URL must be configured.")
    if settings.worker_backend.strip().lower() != "redis":
        errors.append("WORKER_BACKEND must be redis.")
    if settings.vector_backend.strip().lower() != "pgvector":
        errors.append("VECTOR_BACKEND must be pgvector.")
    if settings.embedding_provider.strip().lower() == "fake":
        errors.append("EMBEDDING_PROVIDER cannot be fake.")
    if _is_placeholder(settings.embedding_model):
        errors.append("EMBEDDING_MODEL must be configured.")
    if settings.model_provider_primary.strip().lower() == "fake":
        errors.append("MODEL_PROVIDER_PRIMARY cannot be fake.")

    providers = [
        settings.model_provider_primary.strip().lower(),
        settings.model_provider_fallback.strip().lower(),
    ]
    real_providers = [provider for provider in providers if provider and provider != "fake"]
    if not any(_provider_key_present(settings, provider) for provider in real_providers):
        errors.append("At least one real model provider API key must be configured.")

    if _is_placeholder(settings.cron_secret):
        errors.append("CRON_SECRET must be a non-placeholder secret.")
    if _is_local_url(settings.app_base_url):
        errors.append("APP_BASE_URL must be a public HTTPS URL, not localhost.")
    if settings.frontend_base_url.strip() and _is_local_url(settings.frontend_base_url):
        errors.append("FRONTEND_BASE_URL must not be localhost in production.")

    origins = settings.allowed_origins_list()
    if "*" in origins:
        errors.append("AI_OFFICE_ALLOWED_ORIGINS cannot contain wildcard '*'.")
    if not origins or all(_is_local_url(origin) for origin in origins):
        errors.append("AI_OFFICE_ALLOWED_ORIGINS must include at least one public origin.")

    telegram_enabled = bool(settings.telegram_bot_token.strip())
    if telegram_enabled and _is_placeholder(settings.telegram_webhook_secret):
        errors.append("TELEGRAM_WEBHOOK_SECRET must be configured when Telegram is enabled.")
    if telegram_enabled and not (
        settings.allowed_telegram_user_ids.strip()
        or settings.allowed_telegram_chat_ids.strip()
        or settings.telegram_allowed_chat_ids.strip()
    ):
        errors.append("Telegram allowlist must be configured when Telegram is enabled.")

    if not settings.enable_approval_required:
        errors.append("ENABLE_APPROVAL_REQUIRED must be true in production.")
    if settings.enable_real_tools and not settings.enable_approval_required:
        errors.append("ENABLE_REAL_TOOLS requires ENABLE_APPROVAL_REQUIRED=true.")
    if settings.enable_real_tools and not settings.enable_cost_tracking:
        errors.append("ENABLE_REAL_TOOLS requires audit/cost tracking to remain enabled.")
    if settings.autonomy_enabled and (
        settings.worker_backend.strip().lower() != "redis" or not settings.redis_url.strip()
    ):
        errors.append("AUTONOMY_ENABLED requires Redis worker/scheduler configuration.")

    return errors


def migration_readiness() -> CheckResult:
    """Check that Alembic version metadata exists in the configured DB."""
    try:
        with get_engine().connect() as connection:
            current = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if not current:
            return CheckResult("migrations", False, "alembic_version is empty")
        return CheckResult("migrations", True, f"current revision {current}")
    except Exception as error:
        return CheckResult("migrations", False, str(error))


def run_production_preflight(raise_on_error: bool = True) -> dict[str, Any]:
    """Run production preflight and optionally raise on unsafe configuration."""
    settings = get_settings()
    errors = validate_production_settings(settings)
    checks = [
        {
            "name": "production_settings",
            "ok": not errors,
            "detail": "ok" if not errors else "; ".join(errors),
        }
    ]

    if settings.environment == Environment.PRODUCTION:
        migration = migration_readiness()
        checks.append({"name": migration.name, "ok": migration.ok, "detail": migration.detail})
        if not migration.ok:
            errors.append(f"Migration readiness failed: {migration.detail}")

    result = {
        "environment": settings.environment.value,
        "ok": not errors,
        "errors": errors,
        "checks": checks,
    }
    if raise_on_error and errors:
        raise RuntimeError("Production preflight failed: " + "; ".join(errors))
    return result
