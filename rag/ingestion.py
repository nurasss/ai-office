"""Knowledge ingestion service for DB-backed pilot RAG."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from services.knowledge_service import KnowledgeService


SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf", ".csv", ".json"}


def read_upload_content(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported knowledge file type: {suffix}")
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(data, ensure_ascii=False, indent=2)
    return path.read_text(encoding="utf-8", errors="ignore")


def ingest_text(
    db: Session,
    *,
    workspace_id: str,
    agent_namespace: str,
    title: str,
    source_uri: str,
    file_type: str,
    content: str,
) -> dict[str, object]:
    return KnowledgeService(db).ingest_text(
        workspace_id=workspace_id,
        agent_namespace=agent_namespace,
        title=title,
        source_uri=source_uri,
        file_type=file_type,
        content=content,
    )
