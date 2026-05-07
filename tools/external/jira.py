"""Jira MCP tool — заглушки для работы с задачами."""

from typing import Any

from langchain_core.tools import tool

@tool
async def search_jira_issues(
    jql: str,
    max_results: int = 10,
) -> dict[str, Any]:
    """Поиск задач в Jira по JQL-запросу.

    Args:
        jql: JQL-запрос (напр. 'project = AI AND status = Open').
        max_results: максимальное число результатов.

    Returns:
        Список найденных задач.
    """
    # TODO: реализовать через atlassian-python-api
    return {
        "status": "stub",
        "jql": jql,
        "issues": [],
        "total": 0,
        "message": "Заглушка: подключите JIRA_URL, JIRA_USER, JIRA_API_TOKEN в .env",
    }

@tool
async def create_jira_issue(
    project: str,
    summary: str,
    description: str,
    issue_type: str = "Task",
    priority: str = "Medium",
) -> dict[str, Any]:
    """Создать задачу в Jira.

    Args:
        project: ключ проекта (напр. 'AI').
        summary: заголовок задачи.
        description: описание задачи.
        issue_type: тип (Task, Bug, Story, etc.).
        priority: приоритет (Highest, High, Medium, Low, Lowest).

    Returns:
        Словарь с данными созданной задачи.
    """
    # TODO: реализовать через atlassian-python-api
    return {
        "status": "stub",
        "project": project,
        "summary": summary,
        "issue_type": issue_type,
        "issue_key": None,
        "message": "Заглушка: подключите JIRA_URL, JIRA_USER, JIRA_API_TOKEN в .env",
    }
