"""Fake tools used by tests and no-key development mode."""

from __future__ import annotations

from typing import Any

from tools.base import ToolContext, ToolResult, ToolRisk


class FakeDraftTool:
    name = "fake.draft"
    description = "Create a deterministic local draft without external side effects."
    risk_level = ToolRisk.SAFE_DRAFT
    requires_approval = False

    def dry_run(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(ok=True, data={"draft": args.get("text", "")[:500]}, message="Draft can be created locally.")

    def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(ok=True, data={"draft": args.get("text", "")[:500], "mode": "fake"}, message="Fake draft created.")


class FakeDestructiveTool:
    name = "fake.delete"
    description = "Fake destructive tool for approval-policy tests."
    risk_level = ToolRisk.DELETE_OR_DESTRUCTIVE
    requires_approval = True

    def dry_run(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(ok=True, data={"would_delete": args.get("target", "")}, message="Dry-run only.")

    def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(ok=False, error="Fake destructive execution is disabled.")
