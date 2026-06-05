#!/usr/bin/env python3
"""Scan repository files or release archives for obvious committed secrets."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IGNORED_PATHS = {
    ".env.example",
    ".env.production.example",
    "scripts/check_no_secrets.py",
}
PLACEHOLDER_WORDS = {
    "",
    "change-me",
    "changeme",
    "placeholder",
    "example",
    "test",
    "dummy",
    "fake",
    "none",
    "null",
    "password",
    "ai_office",
    "replace-with-long-random-value",
    "${postgres_password}",
}

TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OpenAI-style API key", re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{12,}\b")),
    ("GitHub personal access token", re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b")),
    ("Slack bot token", re.compile(r"\bxoxb-[A-Za-z0-9-]{20,}\b")),
)
ENV_SECRET_RE = re.compile(
    r"(?m)^\s*(TELEGRAM_BOT_TOKEN|ANTHROPIC_API_KEY|OPENAI_API_KEY|GOOGLE_API_KEY|"
    r"DEEPSEEK_API_KEY|SLACK_BOT_TOKEN|GITHUB_TOKEN|JIRA_API_TOKEN|AI_OFFICE_API_KEY|"
    r"AI_OFFICE_ADMIN_TOKEN|CRON_SECRET)\s*=\s*([^\s#]+)\s*$"
)
DATABASE_URL_RE = re.compile(
    r"postgres(?:ql)?(?:\+\w+)?://(?P<user>[^:\s/]+):(?P<password>[^@\s]+)@",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    path: str
    line_number: int
    kind: str
    snippet: str


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().strip("\"'").lower()
    if normalized in PLACEHOLDER_WORDS:
        return True
    return (
        normalized.startswith("change-me")
        or normalized.startswith("replace-with")
        or normalized.startswith("your-")
        or normalized.startswith("<")
        or normalized.startswith("${")
    )


def _line_is_documented_placeholder(line: str) -> bool:
    lowered = line.lower()
    return any(
        word in lowered
        for word in ("placeholder", "change-me", "replace-with", "example", "dummy", "fake", "test-token")
    )


def scan_text(path: str, text: str) -> list[Finding]:
    if path in IGNORED_PATHS:
        return []

    findings: list[Finding] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if _line_is_documented_placeholder(line):
            continue
        for kind, pattern in TOKEN_PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append(Finding(path, index, kind, _redact(match.group(0))))

        env_match = ENV_SECRET_RE.match(line)
        if env_match and not _is_placeholder(env_match.group(2)):
            findings.append(Finding(path, index, f"{env_match.group(1)} assignment", _redact(env_match.group(2))))

        db_match = DATABASE_URL_RE.search(line)
        if db_match and not _is_placeholder(db_match.group("password")):
            findings.append(Finding(path, index, "Postgres URL with inline password", "postgresql://<user>:***@..."))

    return findings


def _redact(value: str) -> str:
    if len(value) <= 10:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _candidate_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [
        ROOT / item.decode("utf-8", "surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    ]


def _scan_file(path: Path) -> list[Finding]:
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError:
        relative = path.as_posix()
    if relative in IGNORED_PATHS:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    return scan_text(relative, text)


def _scan_zip(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            try:
                data = archive.read(name)
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            findings.extend(scan_text(name, text))
    return findings


def scan_paths(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        if path.suffix == ".zip":
            findings.extend(_scan_zip(path))
        elif path.is_file():
            findings.extend(_scan_file(path.resolve()))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan tracked files or release archives for obvious secrets.")
    parser.add_argument("paths", nargs="*", help="Optional files or zip archives to scan. Defaults to repo candidates.")
    args = parser.parse_args()

    paths = [Path(item) for item in args.paths] if args.paths else _candidate_files()
    findings = scan_paths(paths)
    if findings:
        print("Potential secrets found:")
        for finding in findings:
            print(f"- {finding.path}:{finding.line_number}: {finding.kind}: {finding.snippet}")
        return 1

    print(f"No obvious secrets found in {len(paths)} path(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
