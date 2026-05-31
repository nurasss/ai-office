"""Safe tool adapter contracts for AI Office."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class ToolRisk(str, Enum):
    SAFE_READ = "safe_read"
    SAFE_DRAFT = "safe_draft"
    LOW_RISK_WRITE = "low_risk_write"
    HIGH_RISK_WRITE = "high_risk_write"
    EXTERNAL_SEND = "external_send"
    FINANCIAL_ACTION = "financial_action"
    DELETE_OR_DESTRUCTIVE = "delete_or_destructive"


class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
    requires_approval: bool = False
    approval_id: str | None = None
    error: str | None = None


@dataclass
class ToolContext:
    workspace_id: str = "default"
    task_id: int | None = None
    task_run_id: int | None = None
    agent_run_id: int | None = None
    actor_id: str = "agent"
    agent_name: str = "pmo"


class ToolAdapter(Protocol):
    name: str
    description: str
    risk_level: ToolRisk
    requires_approval: bool

    def dry_run(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        ...

    def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        ...
