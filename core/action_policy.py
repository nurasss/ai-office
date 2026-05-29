"""Safety policy for autonomous actions and developer tools."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.config import get_settings


class ActionDecision(str, Enum):
    SAFE_READ = "safe_read"
    SAFE_PREPARE = "safe_prepare"
    REQUIRES_APPROVAL = "requires_approval"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class PolicyResult:
    decision: ActionDecision
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed_without_approval(self) -> bool:
        return self.decision in {ActionDecision.SAFE_READ, ActionDecision.SAFE_PREPARE}

    @property
    def requires_approval(self) -> bool:
        return self.decision == ActionDecision.REQUIRES_APPROVAL

    @property
    def forbidden(self) -> bool:
        return self.decision == ActionDecision.FORBIDDEN


SAFE_READ_ACTIONS = {
    "list_files",
    "read_file",
    "search_files",
    "git_diff",
    "health_check",
    "memory_search",
}

SAFE_PREPARE_ACTIONS = {
    "create_task",
    "update_task_status",
    "write_plan",
    "write_report",
    "write_draft_file",
    "create_patch",
    "generate_codex_prompt",
    "draft_result",
}

DANGEROUS_KEYWORDS = {
    "deploy",
    "production",
    "prod",
    "merge",
    "push",
    "delete",
    "remove",
    "rm ",
    "drop",
    "truncate",
    "email",
    "рассыл",
    "секрет",
    "secret",
    "env",
    "crm",
    "bitrix",
    "payment",
    "spend",
    "main",
}

FORBIDDEN_COMMAND_TOKENS = {
    "rm",
    "sudo",
    "chmod",
    "chown",
    "curl",
    "wget",
    "ssh",
    "scp",
    "rsync",
    "git",
    "docker",
    "kubectl",
    "vercel",
    "render",
    "heroku",
    "dropdb",
    "psql",
}

SHELL_METACHARS = re.compile(r"[;&|`$<>]")


def classify_action(action_name: str, payload: dict[str, Any] | None = None) -> PolicyResult:
    """Classify a high-level autonomous action."""
    payload = payload or {}
    action_key = action_name.strip().lower()
    searchable = " ".join(str(value).lower() for value in payload.values())

    if action_key in SAFE_READ_ACTIONS:
        return PolicyResult(ActionDecision.SAFE_READ, "Read-only action.")
    if action_key in SAFE_PREPARE_ACTIONS:
        return PolicyResult(ActionDecision.SAFE_PREPARE, "Safe preparation action.")
    if any(keyword in searchable or keyword == action_key for keyword in DANGEROUS_KEYWORDS):
        return PolicyResult(ActionDecision.REQUIRES_APPROVAL, "Dangerous action requires approval.")
    return PolicyResult(ActionDecision.REQUIRES_APPROVAL, "Unknown action requires approval.")


def classify_task(title: str, description: str = "", *, requires_approval: bool = False) -> PolicyResult:
    """Classify an autonomous task before execution."""
    if requires_approval:
        return PolicyResult(ActionDecision.REQUIRES_APPROVAL, "Task explicitly requires approval.")

    text = f"{title}\n{description}".lower()
    if any(keyword in text for keyword in DANGEROUS_KEYWORDS):
        return PolicyResult(ActionDecision.REQUIRES_APPROVAL, "Task text contains a dangerous action.")
    return PolicyResult(ActionDecision.SAFE_PREPARE, "Task can produce a safe draft result.")


def is_safe_command(command: str, safe_commands: list[str] | None = None) -> PolicyResult:
    """Validate a shell command against the configured allowlist."""
    command = command.strip()
    if not command:
        return PolicyResult(ActionDecision.FORBIDDEN, "Empty command is forbidden.")
    if SHELL_METACHARS.search(command):
        return PolicyResult(ActionDecision.FORBIDDEN, "Shell metacharacters are forbidden.")

    try:
        tokens = shlex.split(command)
    except ValueError:
        return PolicyResult(ActionDecision.FORBIDDEN, "Command could not be parsed safely.")
    if not tokens:
        return PolicyResult(ActionDecision.FORBIDDEN, "Empty command is forbidden.")
    if tokens[0] in FORBIDDEN_COMMAND_TOKENS:
        return PolicyResult(ActionDecision.FORBIDDEN, f"Command '{tokens[0]}' is forbidden.")

    allowlist = safe_commands or get_settings().safe_commands_list()
    for allowed in allowlist:
        allowed = allowed.strip()
        if command == allowed or command.startswith(f"{allowed} "):
            return PolicyResult(ActionDecision.SAFE_READ, "Command is allowlisted.")

    return PolicyResult(ActionDecision.REQUIRES_APPROVAL, "Command is not allowlisted.")

