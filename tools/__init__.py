"""MCP-инструменты для агентов."""

from tools.external.github import create_github_pr, read_github_repo
from tools.external.jira import create_jira_issue, search_jira_issues
from tools.external.slack import send_slack_message
from tools.external.db_tools import run_sql_query
from tools.external.erp import parse_invoice_pdf

__all__ = [
    "read_github_repo",
    "create_github_pr",
    "search_jira_issues",
    "create_jira_issue",
    "send_slack_message",
    "run_sql_query",
    "parse_invoice_pdf",
]
