"""Telegram notification tool adapter."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from core.config import get_settings
from tools.base import ToolContext, ToolResult, ToolRisk
from tools.external.telegram import send_telegram_message


class TelegramNotifyArgs(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class TelegramNotifyTool:
    name = "telegram.notify"
    description = "Send a Telegram notification after approval or from trusted system flows."
    risk_level = ToolRisk.EXTERNAL_SEND
    requires_approval = True

    def dry_run(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            parsed = TelegramNotifyArgs(**args)
        except ValidationError as error:
            return ToolResult(ok=False, error=str(error))
        return ToolResult(
            ok=True,
            data={"text_preview": parsed.text[:500], "configured": bool(get_settings().telegram_bot_token.strip())},
            message="Telegram notification would be sent after approval.",
        )

    def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        parsed = TelegramNotifyArgs(**args)
        if not get_settings().enable_real_tools:
            return ToolResult(ok=True, data={"sent": False, "mode": "fake"}, message="Fake Telegram notification recorded.")
        sent = asyncio.run(send_telegram_message(parsed.text))
        return ToolResult(ok=sent, data={"sent": sent}, error=None if sent else "Telegram send failed or is not configured.")
