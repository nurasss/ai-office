from __future__ import annotations

from services.agent_profile_registry import AgentProfileRegistry


def test_backend_api_task_selects_backend_architect():
    profile = AgentProfileRegistry().select_profile_for_task(
        "Design backend API integration endpoints for tasks",
        base_agent="developer",
    )

    assert profile is not None
    assert profile.id == "developer.backend_architect"


def test_mcp_tool_task_selects_mcp_builder():
    profile = AgentProfileRegistry().select_profile_for_task(
        "Build an MCP tool server for safe integrations",
        base_agent="developer",
    )

    assert profile is not None
    assert profile.id == "developer.mcp_builder"


def test_review_pr_task_selects_code_reviewer():
    profile = AgentProfileRegistry().select_profile_for_task(
        "Review the GitHub PR for safety regressions",
        base_agent="developer",
    )

    assert profile is not None
    assert profile.id == "developer.code_reviewer"


def test_docs_task_selects_technical_writer():
    profile = AgentProfileRegistry().select_profile_for_task(
        "Update README and documentation for Telegram commands",
        base_agent="copywriter",
    )

    assert profile is not None
    assert profile.id == "copywriter.technical_writer"


def test_unknown_task_returns_none():
    profile = AgentProfileRegistry().select_profile_for_task(
        "Think about something vague with no operational markers",
        base_agent="developer",
    )

    assert profile is None
