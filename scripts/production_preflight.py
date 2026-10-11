#!/usr/bin/env python3
"""CLI for production/staging preflight checks."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_TEMPLATE_KEYS = {
    "ENVIRONMENT",
    "APP_ENV",
    "APP_BASE_URL",
    "FRONTEND_BASE_URL",
    "AI_OFFICE_REQUIRE_API_KEY",
    "AI_OFFICE_API_KEY",
    "AI_OFFICE_ADMIN_TOKEN",
    "AI_OFFICE_ALLOWED_ORIGINS",
    "CRON_SECRET",
    "DATABASE_URL",
    "REDIS_URL",
    "WORKER_BACKEND",
    "VECTOR_BACKEND",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "MODEL_PROVIDER_PRIMARY",
    "MODEL_PROVIDER_FALLBACK",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_WEBHOOK_SECRET",
    "ALLOWED_TELEGRAM_USER_IDS",
    "ALLOWED_TELEGRAM_CHAT_IDS",
    "ENABLE_REAL_TOOLS",
    "ENABLE_APPROVAL_REQUIRED",
    "ENABLE_PII_REDACTION",
    "ENABLE_COST_TRACKING",
    "ENABLE_RAG_CITATIONS",
    "AI_OFFICE_DAILY_BUDGET_USD",
    "AI_OFFICE_MONTHLY_BUDGET_USD",
    "AI_OFFICE_BUDGET_ENFORCEMENT",
    "AUTONOMY_ENABLED",
}


def _template_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, _ = line.partition("=")
        keys.add(key.strip())
    return keys


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip().strip("\"'")


def _run_template_check(path: Path) -> int:
    keys = _template_keys(path)
    missing = sorted(REQUIRED_TEMPLATE_KEYS - keys)
    print(f"Template: {path}")
    for key in sorted(REQUIRED_TEMPLATE_KEYS):
        marker = "OK" if key in keys else "MISSING"
        print(f"[{marker}] {key}")
    if missing:
        print("Missing required template keys: " + ", ".join(missing))
        return 1
    print("Template structure is complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AI Office production preflight.")
    parser.add_argument("--env-file", help="Load an env file before checking.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero on any preflight error.")
    parser.add_argument("--template-check", action="store_true", help="Check env template structure without requiring real secrets.")
    args = parser.parse_args()

    env_file = Path(args.env_file) if args.env_file else None
    if env_file:
        _load_env_file(env_file)

    if args.template_check:
        if not env_file:
            print("--template-check requires --env-file", file=sys.stderr)
            return 2
        return _run_template_check(env_file)

    from core.config import get_settings
    from core.production import run_production_preflight

    if env_file:
        get_settings.cache_clear()

    result = run_production_preflight(raise_on_error=False)
    print(f"Environment: {result['environment']}")
    for check in result["checks"]:
        marker = "OK" if check["ok"] else "FAIL"
        print(f"[{marker}] {check['name']}: {check['detail']}")

    if result["errors"]:
        print("\nPreflight errors:")
        for error in result["errors"]:
            print(f"- {error}")
        return 1

    if args.strict:
        print("Strict preflight passed.")
    else:
        print("Preflight passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
