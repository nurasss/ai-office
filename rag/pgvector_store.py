"""Postgres-backed knowledge store with deterministic embeddings for pilot mode."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import KnowledgeChunk, KnowledgeDocument


def fake_embedding(text: str, dimensions: int = 16) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [digest[index] / 255 for index in range(dimensions)]
    norm = math.sqrt(sum(value * value for value in values)) or 1
    return [round(value / norm, 6) for value in values]


def lexical_score(query: str, content: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    content_tokens = _tokens(content)
    overlap = query_tokens & content_tokens
    return round(len(overlap) / len(query_tokens), 6)


def create_document(
    db: Session,
    *,
    workspace_id: str,
    agent_namespace: str,
    title: str,
    source_uri: str,
    file_type: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[KnowledgeDocument, list[KnowledgeChunk]]:
    document = KnowledgeDocument(
        workspace_id=workspace_id,
        agent_namespace=agent_namespace,
        title=title,
        source_type="upload",
        source_uri=source_uri,
        file_type=file_type,
        content_hash=_hash(content),
        sensitivity=(metadata or {}).get("sensitivity", "internal"),
    )
    db.add(document)
    db.flush()
    chunks: list[KnowledgeChunk] = []
    for index, chunk_text in enumerate(chunk_text_content(content)):
        chunk = KnowledgeChunk(
            document_id=document.id,
            workspace_id=workspace_id,
            agent_namespace=agent_namespace,
            chunk_index=index,
            content=chunk_text,
            content_hash=_hash(chunk_text),
            metadata_json=metadata or {},
            embedding=fake_embedding(chunk_text),
        )
        db.add(chunk)
        chunks.append(chunk)
    db.flush()
    return document, chunks


def search_chunks(
    db: Session,
    *,
    query: str,
    workspace_id: str,
    allowed_namespaces: list[str],
    top_k: int,
) -> list[dict[str, Any]]:
    stmt = (
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(KnowledgeChunk.workspace_id == workspace_id)
        .where(KnowledgeChunk.agent_namespace.in_(allowed_namespaces))
    )
    results: list[dict[str, Any]] = []
    for chunk, document in db.execute(stmt).all():
        score = lexical_score(query, chunk.content)
        if score <= 0:
            continue
        results.append(
            {
                "document_id": document.id,
                "chunk_id": chunk.id,
                "source_uri": document.source_uri,
                "title": document.title,
                "version": document.version,
                "score": score,
                "agent_namespace": chunk.agent_namespace,
                "content_preview": chunk.content[:500],
                "content": chunk.content,
            }
        )
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:top_k]


def chunk_text_content(content: str, max_chars: int = 1000) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", content) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [content.strip()]:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
        current = paragraph[:max_chars]
    if current:
        chunks.append(current)
    return chunks or [content[:max_chars]]


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[\wа-яА-ЯёЁ]+", text) if len(token) > 2}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
