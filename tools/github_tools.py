"""Safe GitHub tool adapters with dry-run-first writes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError

from core.config import get_settings
from tools.base import ToolContext, ToolResult, ToolRisk
from tools.github_client import GitHubClient, GitHubClientError


class CreateIssueArgs(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    body: str = ""
    owner: str | None = None
    repo: str | None = None


class GitHubCreateIssueTool:
    name = "github.issue.create"
    description = "Create a GitHub issue after approval. Dry-run is always available."
    risk_level = ToolRisk.HIGH_RISK_WRITE
    requires_approval = True

    def dry_run(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            parsed = CreateIssueArgs(**args)
        except ValidationError as error:
            return ToolResult(ok=False, error=str(error))
        settings = get_settings()
        owner = parsed.owner or settings.github_owner or "unknown-owner"
        repo = parsed.repo or settings.github_repo or "unknown-repo"
        return ToolResult(
            ok=True,
            data={
                "dry_run": True,
                "operation": "create_issue",
                "repo": f"{owner}/{repo}",
                "title": parsed.title,
                "body_preview": parsed.body[:500],
                "real_tools_enabled": settings.enable_real_tools,
            },
            message="GitHub issue would be created after approval.",
        )

    def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        settings = get_settings()
        if not settings.enable_real_tools:
            return ToolResult(ok=False, error="ENABLE_REAL_TOOLS=false; no GitHub write was sent.")
        if not settings.github_token.strip():
            return ToolResult(ok=False, error="GITHUB_TOKEN is not configured.")
        dry_run = self.dry_run(args, context)
        if not dry_run.ok:
            return dry_run
        parsed = CreateIssueArgs(**args)
        owner = parsed.owner or settings.github_owner
        repo = parsed.repo or settings.github_repo
        if not owner or not repo:
            return ToolResult(ok=False, error="GITHUB_OWNER and GITHUB_REPO are required.")
        try:
            created = GitHubClient(token=settings.github_token, owner=owner, repo=repo).create_issue(
                title=parsed.title,
                body=parsed.body,
            )
        except GitHubClientError as error:
            return ToolResult(ok=False, error=str(error), data={"dry_run": dry_run.data})
        return ToolResult(
            ok=True,
            data={
                "repo": f"{owner}/{repo}",
                "issue_number": created.get("number"),
                "html_url": created.get("html_url"),
                "title": created.get("title", parsed.title),
            },
            message="GitHub issue created.",
        )


class GitHubReadTool:
    name = "github.issue.read"
    description = "Read GitHub issue metadata. Fake mode returns deterministic data."
    risk_level = ToolRisk.SAFE_READ
    requires_approval = False

    def dry_run(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(ok=True, data={"operation": "read_issue", "args": args}, message="Read operation is safe.")

    def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        settings = get_settings()
        issue_number = args.get("issue_number") or args.get("number") or 0
        if settings.enable_real_tools and settings.github_token.strip() and settings.github_owner and settings.github_repo:
            try:
                data = GitHubClient(
                    token=settings.github_token,
                    owner=settings.github_owner,
                    repo=settings.github_repo,
                ).get_issue(int(issue_number))
            except Exception as error:
                return ToolResult(ok=False, error=str(error))
            return ToolResult(ok=True, data={"issue_number": data.get("number"), "title": data.get("title"), "state": data.get("state"), "html_url": data.get("html_url")})
        return ToolResult(
            ok=True,
            data={
                "issue_number": issue_number,
                "title": f"Fake GitHub issue #{issue_number}",
                "state": "open",
                "mode": "fake",
            },
        )
