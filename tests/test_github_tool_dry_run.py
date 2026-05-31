from tools.base import ToolContext
from tools.github_tools import GitHubCreateIssueTool


def test_github_create_issue_dry_run_has_no_real_side_effect(monkeypatch):
    monkeypatch.setenv("ENABLE_REAL_TOOLS", "false")
    from core.config import get_settings

    get_settings.cache_clear()
    tool = GitHubCreateIssueTool()

    result = tool.dry_run(
        {"title": "Fix RAG namespace isolation", "body": "Details", "owner": "acme", "repo": "office"},
        ToolContext(),
    )

    assert result.ok is True
    assert result.data["dry_run"] is True
    assert result.data["repo"] == "acme/office"
    assert result.data["real_tools_enabled"] is False
