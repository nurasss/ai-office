"""Telegram notification helper for PMO completion events."""

import asyncio
import json
import urllib.parse
import urllib.request

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("tools.telegram")


def _send_telegram_message_sync(token: str, chat_id: str, text: str) -> bool:
    """Send a Telegram message with the standard Bot API."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text[:3900],
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")

    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
        return bool(data.get("ok"))


async def send_telegram_message(text: str) -> bool:
    """Send a Telegram notification if TELEGRAM_* env vars are configured."""
    settings = get_settings()
    token = settings.telegram_bot_token.strip()
    chat_id = settings.telegram_chat_id.strip()

    if not token or not chat_id:
        logger.info("telegram.skipped", reason="not_configured")
        return False

    try:
        sent = await asyncio.to_thread(_send_telegram_message_sync, token, chat_id, text)
        logger.info("telegram.sent", sent=sent)
        return sent
    except Exception as exc:
        logger.error("telegram.error", error=str(exc))
        return False
