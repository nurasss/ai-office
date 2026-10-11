#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE="$ROOT/dist/ai-office-release.zip"

mkdir -p "$ROOT/dist"

python3 - "$ROOT" "$ARCHIVE" <<'PY'
from __future__ import annotations

import fnmatch
import subprocess
import sys
import zipfile
from pathlib import Path

root = Path(sys.argv[1])
archive_path = Path(sys.argv[2])

exclude_patterns = (
    ".env",
    ".env.*",
    ".git/*",
    ".venv/*",
    "venv/*",
    ".vercel/*",
    "__MACOSX/*",
    ".DS_Store",
    "__pycache__/*",
    "*/__pycache__/*",
    "*.pyc",
    ".pytest_cache/*",
    ".ruff_cache/*",
    ".mypy_cache/*",
    "data/*",
    "logs/*",
    "reports/*",
    "generated_sites/*",
    "generated_tools/*",
    "workspaces/*",
    "dist/*",
    "*.zip",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
)
allowed_env_templates = {".env.example", ".env.production.example"}
forbidden_patterns = (
    ".env",
    ".env.*",
    ".git/*",
    ".venv/*",
    ".vercel/*",
    "data/ai_office.db",
    "__pycache__/*",
    "*/__pycache__/*",
    ".pytest_cache/*",
    "*.pyc",
    "*.zip",
)


def included(path: str) -> bool:
    if path in allowed_env_templates:
        return True
    return not any(fnmatch.fnmatch(path, pattern) for pattern in exclude_patterns)


def forbidden(path: str) -> bool:
    if path in allowed_env_templates:
        return False
    return any(fnmatch.fnmatch(path, pattern) for pattern in forbidden_patterns)


result = subprocess.run(
    ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
    cwd=root,
    check=True,
    capture_output=True,
)
files = sorted(
    path.decode("utf-8", "surrogateescape")
    for path in result.stdout.split(b"\0")
    if path and included(path.decode("utf-8", "surrogateescape"))
)

with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(root / path, path)

with zipfile.ZipFile(archive_path) as archive:
    names = archive.namelist()
    bad = [name for name in names if forbidden(name)]

if bad:
    archive_path.unlink(missing_ok=True)
    print("Release archive contains forbidden files:")
    for name in bad:
        print(f"- {name}")
    raise SystemExit(1)

size_mb = archive_path.stat().st_size / (1024 * 1024)
print(f"created={archive_path}")
print(f"files={len(names)}")
print(f"size_mb={size_mb:.2f}")
PY
