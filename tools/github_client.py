"""Minimal GitHub REST client used after approval."""

from __future__ import annotations

from typing import Any

import requests


class GitHubClientError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, *, token: str, owner: str, repo: str, base_url: str = "https://api.github.com") -> None:
        self.token = token
        self.owner = owner
        self.repo = repo
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        response = requests.request(
            method,
            url,
            json=payload,
            timeout=15,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        if response.status_code >= 400:
            raise GitHubClientError(f"GitHub API error {response.status_code}: {response.text[:300]}")
        if not response.content:
            return {}
        data = response.json()
        return data if isinstance(data, dict) else {"items": data}

    @property
    def repo_path(self) -> str:
        return f"/repos/{self.owner}/{self.repo}"

    def repo_metadata(self) -> dict[str, Any]:
        return self._request("GET", self.repo_path)

    def get_issue(self, issue_number: int) -> dict[str, Any]:
        return self._request("GET", f"{self.repo_path}/issues/{issue_number}")

    def create_issue(self, *, title: str, body: str = "") -> dict[str, Any]:
        return self._request("POST", f"{self.repo_path}/issues", {"title": title, "body": body})

    def create_issue_comment(self, *, issue_number: int, body: str) -> dict[str, Any]:
        return self._request("POST", f"{self.repo_path}/issues/{issue_number}/comments", {"body": body})

    def get_pull_request(self, pr_number: int) -> dict[str, Any]:
        return self._request("GET", f"{self.repo_path}/pulls/{pr_number}")

    def create_pr_comment(self, *, pr_number: int, body: str) -> dict[str, Any]:
        return self.create_issue_comment(issue_number=pr_number, body=body)
