"""Safe developer tools for personal autonomous workflows."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from core.action_policy import ActionDecision, classify_action, is_safe_command
from core.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ToolPolicyError(PermissionError):
    """Raised when a tool action violates the safety policy."""


class WorkspaceSandbox:
    """Path-safe workspace wrapper for read-only and draft operations."""

    def __init__(self, root: str | Path | None = None) -> None:
        settings = get_settings()
        configured = Path(root or settings.ai_office_workspace_root).expanduser()
        if not configured.is_absolute():
            configured = PROJECT_ROOT / configured
        self.root = configured.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.drafts_dir = (self.root / "_drafts").resolve()
        self.drafts_dir.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str | Path = ".") -> Path:
        raw = str(relative_path)
        if "\x00" in raw:
            raise ToolPolicyError("Path contains an invalid null byte.")
        target = (self.root / raw).resolve()
        if not target.is_relative_to(self.root):
            raise ToolPolicyError("Path traversal outside AI_OFFICE_WORKSPACE_ROOT is blocked.")
        return target

    def resolve_draft(self, relative_path: str | Path) -> Path:
        target = (self.drafts_dir / str(relative_path)).resolve()
        if not target.is_relative_to(self.drafts_dir):
            raise ToolPolicyError("Draft path traversal is blocked.")
        return target


class DeveloperTools:
    def __init__(self, sandbox: WorkspaceSandbox | None = None) -> None:
        self.sandbox = sandbox or WorkspaceSandbox()

    def list_files(self, path: str = ".") -> list[str]:
        self._assert_action("list_files")
        directory = self.sandbox.resolve(path)
        if not directory.exists():
            return []
        if not directory.is_dir():
            raise ToolPolicyError("list_files expects a directory.")
        return sorted(
            str(item.relative_to(self.sandbox.root))
            for item in directory.iterdir()
            if item.name not in {".git", ".venv", "__pycache__"}
        )

    def read_file(self, path: str, *, max_chars: int = 12000) -> str:
        self._assert_action("read_file")
        target = self.sandbox.resolve(path)
        if not target.is_file():
            raise FileNotFoundError(path)
        return target.read_text(encoding="utf-8", errors="replace")[:max_chars]

    def search_files(self, query: str, path: str = ".") -> list[dict[str, object]]:
        self._assert_action("search_files")
        root = self.sandbox.resolve(path)
        matches: list[dict[str, object]] = []
        for file_path in root.rglob("*"):
            if not file_path.is_file() or any(part in {".git", ".venv", "__pycache__"} for part in file_path.parts):
                continue
            try:
                for line_no, line in enumerate(file_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                    if query.lower() in line.lower():
                        matches.append(
                            {
                                "path": str(file_path.relative_to(self.sandbox.root)),
                                "line": line_no,
                                "preview": line[:220],
                            }
                        )
                        break
            except OSError:
                continue
        return matches[:50]

    def write_draft_file(self, path: str, content: str) -> str:
        self._assert_action("write_draft_file")
        target = self.sandbox.resolve_draft(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return str(target.relative_to(self.sandbox.root))

    def create_patch(self, name: str, patch_text: str) -> str:
        self._assert_action("create_patch")
        safe_name = name if name.endswith(".patch") else f"{name}.patch"
        return self.write_draft_file(safe_name, patch_text)

    def git_diff(self, path: str = ".") -> str:
        self._assert_action("git_diff")
        target = self.sandbox.resolve(path)
        result = subprocess.run(
            ["git", "diff", "--", str(target.relative_to(self.sandbox.root))],
            cwd=self.sandbox.root,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return result.stdout[:20000]

    def run_safe_command(self, command: str, *, cwd: str = ".") -> dict[str, object]:
        policy = is_safe_command(command)
        if policy.decision == ActionDecision.FORBIDDEN:
            raise ToolPolicyError(policy.reason)
        if policy.requires_approval:
            return {
                "status": "waiting_approval",
                "requires_approval": True,
                "reason": policy.reason,
                "command": command,
            }

        working_dir = self.sandbox.resolve(cwd)
        result = subprocess.run(
            shlex.split(command),
            cwd=working_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {
            "status": "completed" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-12000:],
        }

    def generate_codex_prompt(self, task: str, context: str = "") -> str:
        self._assert_action("generate_codex_prompt")
        return (
            "Ты работаешь в локальном репозитории пользователя.\n"
            "Сначала прочитай релевантные файлы, затем внеси минимальные безопасные изменения, "
            "проверь тестами и дай краткий отчет.\n\n"
            f"Задача:\n{task.strip()}\n\n"
            f"Контекст:\n{context.strip()}"
        ).strip()

    def _assert_action(self, action_name: str) -> None:
        policy = classify_action(action_name)
        if policy.forbidden:
            raise ToolPolicyError(policy.reason)
        if policy.requires_approval:
            raise ToolPolicyError(policy.reason)

