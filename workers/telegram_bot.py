"""Telegram companion process for webhook registration and runtime visibility."""

from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request

from core.config import get_settings
from core.logger import get_logger, setup_logging
from core.production import run_production_preflight
from tools.external.telegram import AGENT_TOKEN_FIELDS, get_telegram_bot_token

setup_logging("INFO")
logger = get_logger("workers.telegram_bot")


def _set_webhook_sync(token: str, webhook_url: str, secret: str) -> dict[str, object]:
    payload = urllib.parse.urlencode(
        {
            "url": webhook_url,
            "secret_token": secret,
            "drop_pending_updates": "false",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/setWebhook",
        data=payload,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


async def _register_webhook(token: str, webhook_url: str, secret: str) -> None:
    try:
        result = await asyncio.to_thread(_set_webhook_sync, token, webhook_url, secret)
        logger.info("telegram.webhook.registered", url=webhook_url, ok=bool(result.get("ok")))
    except Exception as error:
        logger.warning("telegram.webhook.register_failed", url=webhook_url, error=str(error))


async def ensure_webhooks() -> None:
    settings = get_settings()
    base_url = settings.app_base_url.rstrip("/")
    secret = settings.telegram_webhook_secret.strip()
    if not base_url or not secret:
        logger.info("telegram.webhook.skipped", reason="missing_app_base_url_or_secret")
        return

    registrations: list[tuple[str, str]] = []
    default_token = get_telegram_bot_token()
    if default_token:
        registrations.append((default_token, f"{base_url}/api/telegram/webhook"))

    for agent_id, field_name in AGENT_TOKEN_FIELDS.items():
        token = str(getattr(settings, field_name, "")).strip()
        if token:
            registrations.append((token, f"{base_url}/api/telegram/webhook/{agent_id}"))

    seen: set[tuple[str, str]] = set()
    for token, webhook_url in registrations:
        pair = (token, webhook_url)
        if pair in seen:
            continue
        seen.add(pair)
        await _register_webhook(token, webhook_url, secret)


async def main() -> None:
    run_production_preflight(raise_on_error=True)
    settings = get_settings()
    logger.info(
        "telegram.bot.started",
        app_base_url=settings.app_base_url,
        has_default_token=bool(get_telegram_bot_token()),
    )
    while True:
        await ensure_webhooks()
        await asyncio.sleep(300)


if __name__ == "__main__":
    asyncio.run(main())
