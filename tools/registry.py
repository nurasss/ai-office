"""Tool registry and policy-aware execution service."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from core.models import Approval, Task, ToolCall, utc_now
from services.audit_service import audit_log
from tools.base import ToolAdapter, ToolContext, ToolResult
from tools.fake_tools import FakeDestructiveTool, FakeDraftTool
from tools.github_tools import GitHubCreateIssueTool, GitHubReadTool
from tools.policy import tool_requires_approval
from tools.sql_tools import SQLReadOnlyTool
from tools.telegram_tools import TelegramNotifyTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolAdapter] = {}

    def register(self, tool: ToolAdapter) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolAdapter:
        try:
            return self._tools[name]
        except KeyError as error:
            raise ValueError(f"Unknown tool: {name}") from error

    def names(self) -> list[str]:
        return sorted(self._tools)


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in [
        FakeDraftTool(),
        FakeDestructiveTool(),
        GitHubReadTool(),
        GitHubCreateIssueTool(),
        TelegramNotifyTool(),
        SQLReadOnlyTool(),
    ]:
        registry.register(tool)
    return registry


class ToolExecutionService:
    def __init__(self, db: Session, registry: ToolRegistry | None = None) -> None:
        self.db = db
        self.registry = registry or build_default_registry()

    def call_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        context: ToolContext,
        *,
        execute: bool = True,
        idempotency_key: str = "",
    ) -> ToolResult:
        tool = self.registry.get(tool_name)
        dry_run_result = tool.dry_run(args, context)
        requires_approval = tool_requires_approval(tool.risk_level, explicit=tool.requires_approval)
        tool_call = ToolCall(
            task_id=context.task_id,
            task_run_id=context.task_run_id,
            agent_run_id=context.agent_run_id,
            tool_name=tool.name,
            arguments_json=args,
            result_json=dry_run_result.model_dump(),
            status="waiting_approval" if requires_approval else "dry_run",
            risk_level=tool.risk_level.value,
            requires_approval=requires_approval,
            idempotency_key=idempotency_key,
        )
        self.db.add(tool_call)
        self.db.flush()
        audit_log(
            self.db,
            workspace_id=context.workspace_id,
            task_id=context.task_id,
            actor_type="tool",
            actor_id=tool.name,
            action="tool.dry_run",
            object_type="tool_call",
            object_id=tool_call.id,
            metadata={"args": args, "result": dry_run_result.model_dump(), "risk_level": tool.risk_level.value},
        )

        if requires_approval:
            approval = Approval(
                task_id=context.task_id,
                tool_call_id=tool_call.id,
                action_type=tool.name,
                tool_name=tool.name,
                risk_level=tool.risk_level.value,
                summary=f"Approval required for {tool.name}",
                reason="Tool policy requires human approval before external/write/destructive action.",
                arguments_json=args,
                dry_run_result=dry_run_result.model_dump(),
                payload={"tool_call_id": tool_call.id, "dry_run": dry_run_result.model_dump()},
                requested_by_agent=context.agent_name,
            )
            self.db.add(approval)
            self.db.flush()
            tool_call.approval_id = approval.id
            if context.task_id is not None:
                task = self.db.get(Task, context.task_id)
                if task:
                    task.status = "waiting_approval"
            audit_log(
                self.db,
                workspace_id=context.workspace_id,
                task_id=context.task_id,
                actor_type="tool",
                actor_id=tool.name,
                action="tool.approval_requested",
                object_type="approval",
                object_id=approval.id,
                metadata={"tool_call_id": tool_call.id, "risk_level": tool.risk_level.value},
            )
            self.db.commit()
            return ToolResult(
                ok=True,
                data=dry_run_result.data,
                message=dry_run_result.message,
                requires_approval=True,
                approval_id=str(approval.id),
            )

        if not execute:
            self.db.commit()
            return dry_run_result

        result = tool.execute(args, context)
        tool_call.result_json = result.model_dump()
        tool_call.status = "completed" if result.ok else "failed"
        tool_call.finished_at = utc_now()
        audit_log(
            self.db,
            workspace_id=context.workspace_id,
            task_id=context.task_id,
            actor_type="tool",
            actor_id=tool.name,
            action="tool.executed" if result.ok else "tool.failed",
            object_type="tool_call",
            object_id=tool_call.id,
            metadata={"result": result.model_dump()},
        )
        self.db.commit()
        return result

    def execute_approved_tool_call(self, tool_call_id: int, *, approved_by: str = "api") -> ToolResult:
        tool_call = self.db.get(ToolCall, tool_call_id)
        if not tool_call:
            return ToolResult(ok=False, error="ToolCall not found.")
        tool = self.registry.get(tool_call.tool_name)
        context = ToolContext(
            workspace_id=tool_call.task.workspace_id if tool_call.task else "default",
            task_id=tool_call.task_id,
            task_run_id=tool_call.task_run_id,
            agent_run_id=tool_call.agent_run_id,
            actor_id=approved_by,
            agent_name="approved",
        )
        result = tool.execute(tool_call.arguments_json or {}, context)
        tool_call.result_json = result.model_dump()
        tool_call.status = "completed" if result.ok else "failed"
        tool_call.finished_at = utc_now()
        if tool_call.task:
            tool_call.task.status = "completed" if result.ok else "failed"
            if result.ok:
                tool_call.task.result_summary = result.message or f"{tool_call.tool_name} executed."
                tool_call.task.result_payload = result.data
        audit_log(
            self.db,
            workspace_id=context.workspace_id,
            task_id=tool_call.task_id,
            actor_type="tool",
            actor_id=tool.name,
            action="tool.executed" if result.ok else "tool.failed",
            object_type="tool_call",
            object_id=tool_call.id,
            metadata={"result": result.model_dump(), "approved_by": approved_by},
        )
        self.db.commit()
        return result
