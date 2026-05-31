"""Knowledge ingestion service for DB-backed pilot RAG."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from rag.pgvector_store import create_document
from services.audit_service import audit_log


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
    document, chunks = create_document(
        db,
        workspace_id=workspace_id,
        agent_namespace=agent_namespace,
        title=title,
        source_uri=source_uri,
        file_type=file_type,
        content=content,
    )
    audit_log(
        db,
        workspace_id=workspace_id,
        actor_type="user",
        actor_id="api",
        action="knowledge.document_uploaded",
        object_type="knowledge_document",
        object_id=document.id,
        metadata={"agent_namespace": agent_namespace, "source_uri": source_uri, "chunks": len(chunks)},
    )
    for chunk in chunks:
        audit_log(
            db,
            workspace_id=workspace_id,
            actor_type="system",
            actor_id="rag_ingestion",
            action="knowledge.chunk_created",
            object_type="knowledge_chunk",
            object_id=chunk.id,
            metadata={"document_id": document.id, "agent_namespace": agent_namespace},
        )
    db.commit()
    return {"document_id": document.id, "chunks": len(chunks)}
