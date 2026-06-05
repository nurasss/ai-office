"""Knowledge storage and retrieval with real embeddings and pgvector search."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import math
import re
from typing import Any, Protocol

import google.generativeai as genai
from openai import OpenAI
from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session

from core.config import get_settings
from core.models import KnowledgeChunk, KnowledgeDocument

DEFAULT_EMBEDDING_DIMENSIONS = 1536


class EmbeddingProviderError(RuntimeError):
    """Raised when no real embedding provider is configured or the call fails."""


@dataclass(slots=True)
class EmbeddingBatch:
    provider: str
    model: str
    dimensions: int
    vectors: list[list[float]]


class EmbeddingProvider(Protocol):
    provider: str
    model: str
    dimensions: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return normalized embeddings for the provided texts."""
        ...


class OpenAIEmbeddingProvider:
    provider = "openai"

    def __init__(self, *, api_key: str, model: str, dimensions: int) -> None:
        self.model = model
        self.dimensions = dimensions
        self.client = OpenAI(api_key=api_key)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions,
        )
        return [
            _normalize_embedding(list(item.embedding), self.dimensions)
            for item in response.data
        ]


class GoogleEmbeddingProvider:
    provider = "google"

    def __init__(self, *, api_key: str, model: str, dimensions: int) -> None:
        self.model = model
        self.dimensions = dimensions
        genai.configure(api_key=api_key)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text_item in texts:
            response = genai.embed_content(
                model=self.model,
                content=text_item,
                task_type="retrieval_document",
                output_dimensionality=self.dimensions,
            )
            embedding = _extract_google_embedding(response)
            vectors.append(_normalize_embedding(embedding, self.dimensions))
        return vectors


def get_embedding_provider() -> EmbeddingProvider:
    """Return the configured real embedding provider."""
    settings = get_settings()
    requested = (settings.embedding_provider or "").strip().lower()
    model = (settings.embedding_model or "").strip()
    dimensions = max(int(getattr(settings, "embedding_dimensions", DEFAULT_EMBEDDING_DIMENSIONS) or DEFAULT_EMBEDDING_DIMENSIONS), 1)

    if requested in {"", "openai"} and settings.openai_api_key.strip():
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key.strip(),
            model=model or "text-embedding-3-small",
            dimensions=dimensions,
        )
    if requested == "google" and settings.google_api_key.strip():
        return GoogleEmbeddingProvider(
            api_key=settings.google_api_key.strip(),
            model=model or "models/text-embedding-004",
            dimensions=dimensions,
        )
    if requested == "openai":
        raise EmbeddingProviderError("EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is missing.")
    if requested == "google":
        raise EmbeddingProviderError("EMBEDDING_PROVIDER=google but GOOGLE_API_KEY is missing.")
    raise EmbeddingProviderError("No real embedding provider is configured.")


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
    """Create one knowledge document and its chunks."""
    chunk_payloads = [
        {
            "content": chunk_text,
            "chunk_index": index,
            "metadata": dict(metadata or {}),
        }
        for index, chunk_text in enumerate(chunk_text_content(content))
    ]
    return _create_document_with_chunks(
        db,
        workspace_id=workspace_id,
        agent_namespace=agent_namespace,
        title=title,
        source_uri=source_uri,
        source_type="upload",
        file_type=file_type,
        metadata=metadata or {},
        chunk_payloads=chunk_payloads,
    )


def upsert_documents(
    db: Session,
    *,
    documents: list[dict[str, Any]],
    workspace_id: str = "default",
) -> int:
    """Upsert generic vector-store documents into the knowledge tables."""
    grouped: dict[tuple[str, str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)

    for index, document in enumerate(documents):
        metadata = dict(document.get("metadata") or {})
        doc_workspace = str(metadata.get("workspace_id") or workspace_id or "default")
        namespace = str(metadata.get("namespace") or "common_corporate")
        source_uri = str(
            metadata.get("source")
            or metadata.get("source_id")
            or document.get("id")
            or f"document-{index}"
        )
        title = str(metadata.get("source_title") or metadata.get("title") or source_uri)
        source_type = str(metadata.get("source_type") or "retriever")
        file_type = str(metadata.get("file_type") or "txt")
        grouped[(doc_workspace, namespace, source_uri, title, source_type, file_type)].append(
            {
                "content": str(document.get("content", "")),
                "chunk_index": int(metadata.get("chunk_index", len(grouped[(doc_workspace, namespace, source_uri, title, source_type, file_type)]))),
                "metadata": metadata,
            }
        )

    created_chunks = 0
    for (
        doc_workspace,
        namespace,
        source_uri,
        title,
        source_type,
        file_type,
    ), chunk_payloads in grouped.items():
        existing_documents = list(
            db.scalars(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.workspace_id == doc_workspace,
                    KnowledgeDocument.agent_namespace == namespace,
                    KnowledgeDocument.source_uri == source_uri,
                )
            )
        )
        for existing_document in existing_documents:
            db.delete(existing_document)
        db.flush()

        _, chunks = _create_document_with_chunks(
            db,
            workspace_id=doc_workspace,
            agent_namespace=namespace,
            title=title,
            source_uri=source_uri,
            source_type=source_type,
            file_type=file_type,
            metadata=chunk_payloads[0].get("metadata", {}) if chunk_payloads else {},
            chunk_payloads=sorted(chunk_payloads, key=lambda item: int(item.get("chunk_index", 0))),
        )
        created_chunks += len(chunks)
    return created_chunks


def search_chunks(
    db: Session,
    *,
    query: str,
    workspace_id: str,
    allowed_namespaces: list[str],
    top_k: int,
) -> list[dict[str, Any]]:
    """Search knowledge chunks using pgvector, then Python cosine, then lexical fallback."""
    try:
        embedding_batch = _embed_query(query)
        if embedding_batch is not None:
            query_embedding = embedding_batch.vectors[0]
            if _is_postgres(db):
                try:
                    pgvector_results = _search_pgvector(
                        db,
                        query_embedding=query_embedding,
                        workspace_id=workspace_id,
                        allowed_namespaces=allowed_namespaces,
                        top_k=top_k,
                    )
                    if pgvector_results:
                        return pgvector_results
                except Exception:
                    pass

            python_vector_results = _search_python_vectors(
                db,
                query_embedding=query_embedding,
                workspace_id=workspace_id,
                allowed_namespaces=allowed_namespaces,
                top_k=top_k,
            )
            if python_vector_results:
                return python_vector_results
    except Exception:
        pass

    if not get_settings().rag_lexical_fallback_enabled:
        return []
    try:
        return _search_lexical(
            db,
            query=query,
            workspace_id=workspace_id,
            allowed_namespaces=allowed_namespaces,
            top_k=top_k,
        )
    except Exception:
        return []


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


def lexical_score(query: str, content: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    content_tokens = _tokens(content)
    overlap = query_tokens & content_tokens
    return round(len(overlap) / len(query_tokens), 6)


def _create_document_with_chunks(
    db: Session,
    *,
    workspace_id: str,
    agent_namespace: str,
    title: str,
    source_uri: str,
    source_type: str,
    file_type: str,
    metadata: dict[str, Any],
    chunk_payloads: list[dict[str, Any]],
) -> tuple[KnowledgeDocument, list[KnowledgeChunk]]:
    combined_content = "\n\n".join(str(payload.get("content", "")) for payload in chunk_payloads)
    document = KnowledgeDocument(
        workspace_id=workspace_id,
        agent_namespace=agent_namespace,
        title=title,
        source_type=source_type,
        source_uri=source_uri,
        file_type=file_type,
        content_hash=_hash(combined_content),
        sensitivity=(metadata or {}).get("sensitivity", "internal"),
    )
    db.add(document)
    db.flush()

    embedding_batch = _embed_texts([str(payload.get("content", "")) for payload in chunk_payloads])
    chunks: list[KnowledgeChunk] = []
    for index, payload in enumerate(chunk_payloads):
        chunk_text = str(payload.get("content", ""))
        vector = embedding_batch.vectors[index] if embedding_batch is not None else None
        chunk = KnowledgeChunk(
            document_id=document.id,
            workspace_id=workspace_id,
            agent_namespace=agent_namespace,
            chunk_index=int(payload.get("chunk_index", index) or index),
            content=chunk_text,
            content_hash=_hash(chunk_text),
            metadata_json=dict(payload.get("metadata") or metadata or {}),
            embedding_model=embedding_batch.model if embedding_batch is not None else "",
            embedding_dimensions=embedding_batch.dimensions if embedding_batch is not None else 0,
            embedding=vector,
        )
        db.add(chunk)
        chunks.append(chunk)
    db.flush()

    if embedding_batch is not None and _is_postgres(db):
        for chunk in chunks:
            if chunk.embedding:
                _update_pgvector_column(db, chunk.id, chunk.embedding)
    db.flush()
    return document, chunks


def _embed_query(query: str) -> EmbeddingBatch | None:
    return _embed_texts([query])


def _embed_texts(texts: list[str]) -> EmbeddingBatch | None:
    try:
        provider = get_embedding_provider()
    except EmbeddingProviderError:
        return None
    vectors = provider.embed_texts(texts)
    return EmbeddingBatch(
        provider=provider.provider,
        model=provider.model,
        dimensions=provider.dimensions,
        vectors=vectors,
    )


def _search_pgvector(
    db: Session,
    *,
    query_embedding: list[float],
    workspace_id: str,
    allowed_namespaces: list[str],
    top_k: int,
) -> list[dict[str, Any]]:
    settings = get_settings()
    metric = (settings.pgvector_similarity_metric or "cosine").strip().lower()
    if metric == "inner_product":
        score_sql = "-1 * (kc.embedding_vector <#> CAST(:query_vector AS vector))"
        order_sql = "kc.embedding_vector <#> CAST(:query_vector AS vector)"
    else:
        score_sql = "1 - (kc.embedding_vector <=> CAST(:query_vector AS vector))"
        order_sql = "kc.embedding_vector <=> CAST(:query_vector AS vector)"

    stmt = text(
        f"""
        SELECT
            kc.id AS chunk_id,
            kc.document_id AS document_id,
            kc.agent_namespace AS agent_namespace,
            kc.content AS content,
            kd.source_uri AS source_uri,
            kd.title AS title,
            kd.version AS version,
            {score_sql} AS score
        FROM knowledge_chunks kc
        JOIN knowledge_documents kd ON kd.id = kc.document_id
        WHERE kc.workspace_id = :workspace_id
          AND kc.agent_namespace IN :allowed_namespaces
          AND kc.embedding_vector IS NOT NULL
        ORDER BY {order_sql}
        LIMIT :top_k
        """
    ).bindparams(bindparam("allowed_namespaces", expanding=True))
    rows = db.execute(
        stmt,
        {
            "workspace_id": workspace_id,
            "allowed_namespaces": allowed_namespaces,
            "query_vector": _vector_literal(query_embedding),
            "top_k": top_k,
        },
    ).mappings()
    return [
        {
            "document_id": int(row["document_id"]),
            "chunk_id": int(row["chunk_id"]),
            "source_uri": str(row["source_uri"]),
            "title": str(row["title"]),
            "version": int(row["version"]),
            "score": float(row["score"] or 0.0),
            "agent_namespace": str(row["agent_namespace"]),
            "content_preview": str(row["content"])[:500],
            "content": str(row["content"]),
            "chunk": str(row["content"]),
        }
        for row in rows
    ]


def _search_python_vectors(
    db: Session,
    *,
    query_embedding: list[float],
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
        chunk_embedding = list(chunk.embedding or [])
        if not chunk_embedding:
            continue
        score = cosine_similarity(query_embedding, chunk_embedding)
        if score <= 0:
            continue
        results.append(_chunk_result(document=document, chunk=chunk, score=score))
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:top_k]


def _search_lexical(
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
        results.append(_chunk_result(document=document, chunk=chunk, score=score))
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:top_k]


def _chunk_result(
    *,
    document: KnowledgeDocument,
    chunk: KnowledgeChunk,
    score: float,
) -> dict[str, Any]:
    return {
        "document_id": document.id,
        "chunk_id": chunk.id,
        "source_uri": document.source_uri,
        "title": document.title,
        "version": document.version,
        "score": round(float(score), 6),
        "agent_namespace": chunk.agent_namespace,
        "content_preview": chunk.content[:500],
        "content": chunk.content,
        "chunk": chunk.content,
    }


def _update_pgvector_column(db: Session, chunk_id: int, embedding: list[float]) -> None:
    db.execute(
        text(
            """
            UPDATE knowledge_chunks
            SET embedding_vector = CAST(:embedding_vector AS vector)
            WHERE id = :chunk_id
            """
        ),
        {
            "chunk_id": chunk_id,
            "embedding_vector": _vector_literal(embedding),
        },
    )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    numerator = sum(float(left[index]) * float(right[index]) for index in range(size))
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left[:size])) or 1.0
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right[:size])) or 1.0
    return numerator / (left_norm * right_norm)


def _extract_google_embedding(response: Any) -> list[float]:
    if isinstance(response, dict):
        if isinstance(response.get("embedding"), dict):
            values = response["embedding"].get("values")
            if isinstance(values, list):
                return [float(value) for value in values]
        if isinstance(response.get("embedding"), list):
            return [float(value) for value in response["embedding"]]
    embedding = getattr(response, "embedding", None)
    if isinstance(embedding, dict) and isinstance(embedding.get("values"), list):
        return [float(value) for value in embedding["values"]]
    if isinstance(embedding, list):
        return [float(value) for value in embedding]
    raise EmbeddingProviderError("Google embedding response did not contain an embedding vector.")


def _normalize_embedding(values: list[float], dimensions: int) -> list[float]:
    normalized = [float(value) for value in values[:dimensions]]
    if len(normalized) < dimensions:
        normalized.extend([0.0] * (dimensions - len(normalized)))
    norm = math.sqrt(sum(value * value for value in normalized)) or 1.0
    return [round(value / norm, 8) for value in normalized]


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[\wа-яА-ЯёЁ]+", text) if len(token) > 2}


def _hash(text_value: str) -> str:
    return hashlib.sha256(text_value.encode("utf-8")).hexdigest()


def _is_postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"
