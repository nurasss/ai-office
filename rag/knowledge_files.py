"""Lightweight keyword search over committed knowledge files.

The local JSON vector store lives under ``data/`` and is intentionally ignored
by git. This module gives deployed previews a deterministic fallback over the
committed ``knowledge/`` markdown files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from rag.namespaces import get_agent_profile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge"
SUPPORTED_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".sql"}


@dataclass(frozen=True)
class KnowledgeFileHit:
    """A ranked local knowledge file match."""

    path: Path
    content: str
    score: int
    namespace: str
    agent_id: str

    @property
    def source(self) -> str:
        return self.path.relative_to(PROJECT_ROOT).as_posix()


def search_knowledge_files(
    agent_id: str,
    query: str,
    *,
    top_k: int = 3,
) -> list[KnowledgeFileHit]:
    """Search common + agent-specific knowledge files by token overlap."""
    if not KNOWLEDGE_ROOT.exists():
        return []

    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    hits: list[KnowledgeFileHit] = []
    for root, owner, namespace in _knowledge_roots(agent_id):
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue

            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="utf-8", errors="ignore")

            score = _score(path, content, query_tokens)
            if score <= 0:
                continue

            hits.append(
                KnowledgeFileHit(
                    path=path,
                    content=content.strip(),
                    score=score,
                    namespace=namespace,
                    agent_id=owner,
                )
            )

    return sorted(hits, key=lambda hit: (hit.score, hit.source), reverse=True)[:top_k]


def format_knowledge_file_context(
    hits: list[KnowledgeFileHit],
    *,
    max_chars_per_file: int = 6000,
) -> str:
    """Render file hits as a compact LLM context block."""
    if not hits:
        return ""

    lines = ["Контекст из файлов knowledge/:"]
    for index, hit in enumerate(hits, start=1):
        content = hit.content
        if len(content) > max_chars_per_file:
            content = f"{content[:max_chars_per_file]}..."

        lines.append(
            f"[{index}] source={hit.source} namespace={hit.namespace} score={hit.score}\n"
            f"{content}"
        )

    return "\n\n".join(lines)


def _knowledge_roots(agent_id: str) -> list[tuple[Path, str, str]]:
    roots = [(KNOWLEDGE_ROOT / "common", "common", "common_corporate")]
    if agent_id != "common":
        roots.append(
            (
                KNOWLEDGE_ROOT / agent_id,
                agent_id,
                get_agent_profile(agent_id)["namespace"],
            )
        )
    return roots


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_]{3,}", str(text).lower())
        if token
    }


def _score(path: Path, content: str, query_tokens: set[str]) -> int:
    content_tokens = _tokens(content)
    name_tokens = _tokens(path.stem.replace("_", " ").replace("-", " "))
    return len(query_tokens.intersection(content_tokens)) + len(
        query_tokens.intersection(name_tokens)
    )
