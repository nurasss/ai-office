from __future__ import annotations

import pytest

from core.action_policy import ActionDecision, classify_task, is_safe_command
from core.config import get_settings
from services.developer_tools import DeveloperTools, ToolPolicyError, WorkspaceSandbox
from services.pmo_planner import PMOPlanningService


def test_pmo_structured_plan_from_valid_json():
    plan = PMOPlanningService().plan_from_text(
        goal="Сделать autonomous core",
        llm_text="""
        {
          "project_slug": "ai-office",
          "goal": "Сделать autonomous core",
          "tasks": [
            {
              "title": "Добавить API auth",
              "description": "Закрыть private endpoints",
              "assigned_agent": "developer",
              "priority": 1,
              "requires_approval": false
            }
          ]
        }
        """,
    )

    assert plan.project_slug == "ai-office"
    assert plan.tasks[0].assigned_agent == "developer"
    assert not plan.fallback_used


def test_pmo_fallback_plan_for_invalid_json():
    plan = PMOPlanningService().plan_from_text(
        goal="Deploy AI Office to production",
        llm_text="not-json",
    )

    assert plan.fallback_used
    assert plan.tasks
    assert plan.tasks[0].requires_approval


def test_tools_policy_blocks_path_traversal(tmp_path):
    sandbox = WorkspaceSandbox(tmp_path)
    tools = DeveloperTools(sandbox)

    with pytest.raises(ToolPolicyError):
        tools.read_file("../secret.txt")


def test_tools_policy_blocks_forbidden_commands():
    assert is_safe_command("rm -rf .").decision == ActionDecision.FORBIDDEN
    assert is_safe_command("pytest").decision == ActionDecision.SAFE_READ


def test_run_safe_command_allows_allowlisted_command(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OFFICE_SAFE_COMMANDS", "python3 -V")
    get_settings.cache_clear()

    tools = DeveloperTools(WorkspaceSandbox(tmp_path))
    result = tools.run_safe_command("python3 -V")

    assert result["status"] == "completed"


def test_dangerous_task_requires_approval():
    policy = classify_task("Push changes to main", "git push origin main")

    assert policy.requires_approval

