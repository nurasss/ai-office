from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from core.models import ToolCall
from core.schemas import TaskCreate
from services.approval_service import ApprovalService
from services.task_service import TaskService
from tools.base import ToolContext
from tools.registry import ToolExecutionService


class FakeGitHubClient:
    calls = []

    def __init__(self, *, token, owner, repo, base_url="https://api.github.com"):
        self.token = token
        self.owner = owner
        self.repo = repo

    def create_issue(self, *, title: str, body: str = ""):
        self.calls.append({"title": title, "body": body, "token": self.token})
        return {"number": 42, "html_url": "https://example.test/issues/42", "title": title}


def test_github_write_executes_only_after_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'github.db'}")
    monkeypatch.setenv("ENABLE_REAL_TOOLS", "true")
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.setenv("GITHUB_OWNER", "owner")
    monkeypatch.setenv("GITHUB_REPO", "repo")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    FakeGitHubClient.calls = []
    monkeypatch.setattr("tools.github_tools.GitHubClient", FakeGitHubClient)

    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Create issue", input_text="Создай GitHub issue"))
        result = ToolExecutionService(db).call_tool(
            "github.issue.create",
            {"title": "Fix", "body": "Details"},
            ToolContext(task_id=task.id, workspace_id="default", agent_name="developer"),
        )
        assert FakeGitHubClient.calls == []

        approval = ApprovalService(db).approve(int(result.approval_id), approved_by="manager")
        tool_call = db.get(ToolCall, approval.tool_call_id)

        assert approval.status == "approved"
        assert FakeGitHubClient.calls and FakeGitHubClient.calls[0]["token"] == "fake-token"
        assert tool_call.status == "completed"
        assert tool_call.result_json["data"]["issue_number"] == 42
