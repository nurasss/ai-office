"""GitHub MCP tool — заглушки для работы с репозиториями."""

from typing import Any

from langchain_core.tools import tool

@tool
async def read_github_repo(
    repo: str,
    path: str = "",
    branch: str = "main",
) -> dict[str, Any]:
    """Прочитать файлы из GitHub-репозитория.

    Args:
        repo: имя репозитория (owner/repo).
        path: путь к файлу или директории.
        branch: ветка (по умолчанию main).

    Returns:
        Словарь с содержимым файлов и метаданными.
    """
    # TODO: реализовать через PyGithub + GITHUB_TOKEN
    return {
        "status": "stub",
        "repo": repo,
        "path": path,
        "branch": branch,
        "files": [],
        "message": "Заглушка: подключите GITHUB_TOKEN в .env",
    }

@tool
async def create_github_pr(
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main",
) -> dict[str, Any]:
    """Создать Pull Request на GitHub.

    Args:
        repo: имя репозитория (owner/repo).
        title: заголовок PR.
        body: описание PR.
        head: исходная ветка.
        base: целевая ветка.

    Returns:
        Словарь с данными созданного PR.
    """
    # TODO: реализовать через PyGithub
    return {
        "status": "stub",
        "repo": repo,
        "title": title,
        "head": head,
        "base": base,
        "pr_number": None,
        "message": "Заглушка: подключите GITHUB_TOKEN в .env",
    }
