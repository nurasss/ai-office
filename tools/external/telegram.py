"""Telegram Bot API helpers for notifications and chat webhooks."""

from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("tools.telegram")

AGENT_TOKEN_FIELDS = {
    "pmo": "telegram_pmo_bot_token",
    "data_analyst": "telegram_data_analyst_bot_token",
    "developer": "telegram_developer_bot_token",
    "copywriter": "telegram_copywriter_bot_token",
    "support": "telegram_support_bot_token",
    "strategist": "telegram_strategist_bot_token",
    "accountant": "telegram_accountant_bot_token",
}


def get_telegram_bot_token(agent_id: str | None = None) -> str:
    """Return an agent-specific bot token with fallback to the legacy token."""
    settings = get_settings()
    if agent_id:
        field_name = AGENT_TOKEN_FIELDS.get(agent_id)
        if field_name:
            token = str(getattr(settings, field_name, "")).strip()
            if token:
                return token
    return settings.telegram_bot_token.strip()


def _send_telegram_message_sync(
    token: str,
    chat_id: str,
    text: str,
    *,
    reply_to_message_id: int | None = None,
    message_thread_id: int | None = None,
) -> bool:
    """Send a Telegram message with the standard Bot API."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload_data = {
        "chat_id": chat_id,
        "text": text[:3900],
        "disable_web_page_preview": "true",
    }
    if reply_to_message_id is not None:
        payload_data["reply_to_message_id"] = str(reply_to_message_id)
    if message_thread_id is not None:
        payload_data["message_thread_id"] = str(message_thread_id)

    payload = urllib.parse.urlencode(payload_data).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")

    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
        return bool(data.get("ok"))


async def send_telegram_message(text: str) -> bool:
    """Send a Telegram notification if TELEGRAM_* env vars are configured."""
    settings = get_settings()
    token = get_telegram_bot_token()
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


async def send_telegram_message_to(
    chat_id: str | int,
    text: str,
    *,
    agent_id: str | None = None,
    reply_to_message_id: int | None = None,
    message_thread_id: int | None = None,
) -> bool:
    """Send a Telegram message to the chat that triggered a webhook."""
    token = get_telegram_bot_token(agent_id)

    if not token:
        logger.info("telegram.skipped", reason="token_not_configured")
        return False

    try:
        sent = await asyncio.to_thread(
            _send_telegram_message_sync,
            token,
            str(chat_id),
            text,
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
        )
        logger.info("telegram.sent_to_chat", sent=sent, chat_id=str(chat_id))
        return sent
    except Exception as exc:
        logger.error("telegram.error", chat_id=str(chat_id), error=str(exc))
        return False
