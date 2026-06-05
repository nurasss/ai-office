"""Simple vector-store interfaces and a local JSON fallback backend."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from sqlalchemy import select

from core.config import get_settings
from core.db import get_session, init_db, should_auto_create_tables
from core.models import KnowledgeDocument
from rag.pgvector_store import search_chunks
from services.knowledge_service import KnowledgeService

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCAL_JSON_PATH = PROJECT_ROOT / "data" / "vector_store" / "documents.jsonl"


class BaseVectorStore(ABC):
    """Minimal async interface used by the RAG retriever."""

    @abstractmethod
    async def upsert(self, documents: list[dict[str, Any]]) -> None:
        """Insert or replace documents."""
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return documents relevant to the query."""
        ...

    @abstractmethod
    async def delete(self, ids: list[str]) -> None:
        """Delete documents by id."""
        ...


class LocalJsonVectorStore(BaseVectorStore):
    """Tiny JSONL document store with token-overlap ranking.

    It is intentionally boring: good enough for local smoke tests, serverless
    demos, and the Pixel Office UI without requiring Postgres or Pinecone.
    """

    def __init__(self, path: str | Path = DEFAULT_LOCAL_JSON_PATH) -> None:
        self.path = Path(path)
        self._writable = self._probe_writable()

    async def upsert(self, documents: list[dict[str, Any]]) -> None:
        if not self._writable:
            return
        existing = {str(document.get("id", "")): document for document in self._read_all()}
        for index, document in enumerate(documents):
            document_id = str(document.get("id") or self._stable_id(document, index))
            stored = dict(document)
            stored["id"] = document_id
            stored.setdefault("metadata", {})
            existing[document_id] = stored
        self._write_all(list(existing.values()))

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []

        query_tokens = _tokens(query)
        matches: list[dict[str, Any]] = []
        for document in self._read_all():
            if not _matches_filters(document.get("metadata", {}), filters or {}):
                continue
            content = str(document.get("content", ""))
            score = _score(query_tokens, content)
            if score <= 0 and query_tokens:
                continue
            result = dict(document)
            result["score"] = score
            matches.append(result)

        matches.sort(key=lambda item: item.get("score", 0), reverse=True)
        return matches[:top_k]

    async def delete(self, ids: list[str]) -> None:
        if not self._writable:
            return
        id_set = {str(item) for item in ids}
        self._write_all(
            [document for document in self._read_all() if str(document.get("id", "")) not in id_set]
        )

    def _probe_writable(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        return True

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        documents: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    documents.append(item)
        return documents

    def _write_all(self, documents: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            for document in documents:
                file.write(json.dumps(document, ensure_ascii=False) + "\n")
        tmp_path.replace(self.path)

    @staticmethod
    def _stable_id(document: dict[str, Any], index: int) -> str:
        metadata = document.get("metadata") or {}
        source = str(metadata.get("source") or metadata.get("source_id") or "document")
        return f"{source}:{index}"


class PgVectorStore(BaseVectorStore):
    """DB-backed pgvector store with local emergency fallback only when required."""

    async def upsert(self, documents: list[dict[str, Any]]) -> None:
        if should_auto_create_tables():
            init_db()
        with get_session() as db:
            KnowledgeService(db).upsert_retriever_documents(documents=documents)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if should_auto_create_tables():
            init_db()
        filters = filters or {}
        workspace_id = str(filters.get("workspace_id") or "default")
        namespace_filter = filters.get("namespace") or {}
        allowed_namespaces = _normalize_namespace_filter(namespace_filter)
        if not allowed_namespaces:
            return []

        with get_session() as db:
            results = search_chunks(
                db,
                query=query,
                workspace_id=workspace_id,
                allowed_namespaces=allowed_namespaces,
                top_k=top_k,
            )

        allowed_set = set(allowed_namespaces)
        agent_id_filter = filters.get("agent_id")
        allowed_agent_ids = set(_normalize_agent_filter(agent_id_filter)) if agent_id_filter else None
        normalized: list[dict[str, Any]] = []
        for result in results:
            namespace = str(result.get("agent_namespace", ""))
            if namespace not in allowed_set:
                continue
            metadata = {
                "namespace": namespace,
                "source": result.get("source_uri", ""),
                "source_id": result.get("source_uri", ""),
            }
            source_uri = str(result.get("source_uri", ""))
            agent_id = _infer_agent_id_from_namespace(namespace, source_uri)
            if agent_id:
                metadata["agent_id"] = agent_id
            if allowed_agent_ids is not None and metadata.get("agent_id") not in allowed_agent_ids:
                continue
            normalized.append(
                {
                    "id": f"knowledge_chunk:{result.get('chunk_id')}",
                    "content": result.get("chunk", "") or result.get("content", ""),
                    "score": float(result.get("score", 0.0) or 0.0),
                    "metadata": metadata,
                }
            )
        return normalized[:top_k]

    async def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        if should_auto_create_tables():
            init_db()
        source_uris = {
            item.split(":", 1)[1]
            for item in ids
            if ":" in item and item.split(":", 1)[0] == "source"
        }
        if not source_uris:
            return
        with get_session() as db:
            documents = list(
                db.scalars(
                    select(KnowledgeDocument).where(KnowledgeDocument.source_uri.in_(source_uris))
                )
            )
            for document in documents:
                db.delete(document)
            db.commit()


class PineconeVectorStore(LocalJsonVectorStore):
    """Local fallback for Pinecone until a hosted vector index is configured."""


def create_vector_store(backend: str | None = None) -> BaseVectorStore:
    """Create the configured vector store.

    The local JSON backend remains available for serverless/demo mode.
    """
    selected = (backend or "local_json").strip().lower()
    settings = get_settings()
    configured_path = getattr(settings, "local_vector_store_path", "")
    local_path = Path(configured_path or DEFAULT_LOCAL_JSON_PATH)
    if not local_path.is_absolute():
        local_path = PROJECT_ROOT / local_path

    if selected == "local_json":
        return LocalJsonVectorStore(local_path)
    if selected == "pgvector":
        return PgVectorStore()
    if selected == "pinecone":
        return PineconeVectorStore(local_path)
    raise ValueError(f"Unknown vector store backend: {backend}")


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[\wа-яА-ЯёЁ]+", text) if len(token) > 2}


def _score(query_tokens: set[str], content: str) -> float:
    if not query_tokens:
        return 0
    content_tokens = _tokens(content)
    if not content_tokens:
        return 0
    overlap = query_tokens & content_tokens
    return len(overlap) / max(len(query_tokens), 1)


def _matches_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        actual = metadata.get(key)
        if isinstance(expected, dict) and "$in" in expected:
            if actual not in set(expected["$in"]):
                return False
            continue
        if actual != expected:
            return False
    return True


def _normalize_namespace_filter(value: Any) -> list[str]:
    if isinstance(value, dict) and "$in" in value:
        value = value["$in"]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []


def _normalize_agent_filter(value: Any) -> list[str]:
    if isinstance(value, dict) and "$in" in value:
        value = value["$in"]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []


def _infer_agent_id_from_namespace(namespace: str, source_uri: str) -> str:
    if namespace.startswith("agent_"):
        suffix = namespace.removeprefix("agent_")
        if suffix == "analyst":
            return "data_analyst"
        return suffix
    source_parts = Path(source_uri).parts
    if "knowledge" in source_parts:
        try:
            knowledge_index = source_parts.index("knowledge")
            candidate = source_parts[knowledge_index + 1]
        except (ValueError, IndexError):
            return "common"
        if candidate == "common":
            return "common"
        if candidate == "data_analyst":
            return "data_analyst"
        return candidate
    return "common"
