"""Slack MCP tool — заглушки для отправки сообщений."""

from typing import Any, Optional

from langchain_core.tools import tool

@tool
async def send_slack_message(
    channel: str,
    text: str,
    thread_ts: Optional[str] = None,
) -> dict[str, Any]:
    """Отправить сообщение в Slack-канал.

    Args:
        channel: имя или ID канала (напр. '#general' или 'C01234').
        text: текст сообщения (поддерживает Markdown).
        thread_ts: timestamp треда для ответа в треде (опционально).

    Returns:
        Статус отправки и timestamp сообщения.
    """
    # TODO: реализовать через slack_sdk.WebClient
    return {
        "status": "stub",
        "channel": channel,
        "text": text[:100] + "..." if len(text) > 100 else text,
        "ts": None,
        "message": "Заглушка: подключите SLACK_BOT_TOKEN в .env",
    }
