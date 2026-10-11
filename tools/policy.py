"""Tool execution policy."""

from __future__ import annotations

from core.config import get_settings
from tools.base import ToolRisk


ALWAYS_APPROVAL = {
    ToolRisk.HIGH_RISK_WRITE,
    ToolRisk.EXTERNAL_SEND,
    ToolRisk.FINANCIAL_ACTION,
    ToolRisk.DELETE_OR_DESTRUCTIVE,
}


def tool_requires_approval(risk_level: ToolRisk, *, explicit: bool = False) -> bool:
    settings = get_settings()
    if risk_level in {ToolRisk.SAFE_READ, ToolRisk.SAFE_DRAFT}:
        return False
    if risk_level == ToolRisk.LOW_RISK_WRITE:
        return explicit or settings.enable_approval_required
    if risk_level in ALWAYS_APPROVAL:
        return True
    return True
