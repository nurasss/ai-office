"""Vector Store — локальный dev-store, заглушки под pgvector и Pinecone."""

from abc import ABC, abstractmethod
import json
import re
from pathlib import Path
from typing import Any, Optional

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("rag.vector_store")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCAL_STORE_PATH = PROJECT_ROOT / "data" / "vector_store" / "documents.jsonl"

class BaseVectorStore(ABC):
    """Абстрактный векторный стор."""

    @abstractmethod
    async def upsert(self, documents: list[dict[str, Any]]) -> None:
        """Добавить или обновить документы."""
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Поиск ближайших документов."""
        ...

    @abstractmethod
    async def delete(self, ids: list[str]) -> None:
        """Удалить документы по ID."""
        ...

class LocalJsonVectorStore(BaseVectorStore):
    """Простой локальный vector-like store для dev/smoke-прогонов без Postgres.

    Это не замена production-векторной БД: поиск основан на overlap токенов.
    Зато backend реально сохраняет ingest-чанки и уважает namespace-фильтры.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or DEFAULT_LOCAL_STORE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def upsert(self, documents: list[dict[str, Any]]) -> None:
        """Добавить или обновить документы в JSONL-файле."""
        existing = {document["id"]: document for document in self._read_documents()}
        for document in documents:
            document_id = document.get("id")
            if not document_id:
                continue
            existing[str(document_id)] = document

        with open(self.path, "w", encoding="utf-8") as file:
            for document in existing.values():
                file.write(json.dumps(document, ensure_ascii=False) + "\n")

        logger.info("local_json.upsert", count=len(documents), path=str(self.path))

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Найти документы через простой token-overlap ranking."""
        query_tokens = _tokens(query)
        candidates = [
            document
            for document in self._read_documents()
            if _matches_filters(document.get("metadata", {}), filters or {})
        ]
        ranked = sorted(
            candidates,
            key=lambda document: _score_document(document, query_tokens),
            reverse=True,
        )
        results = [
            dict(document, score=_score_document(document, query_tokens))
            for document in ranked
            if _score_document(document, query_tokens) > 0
        ][:top_k]

        logger.info(
            "local_json.search",
            query=query[:100],
            top_k=top_k,
            results=len(results),
        )
        return results

    async def delete(self, ids: list[str]) -> None:
        """Удалить документы по ID."""
        ids_to_delete = set(ids)
        remaining = [
            document
            for document in self._read_documents()
            if document.get("id") not in ids_to_delete
        ]
        with open(self.path, "w", encoding="utf-8") as file:
            for document in remaining:
                file.write(json.dumps(document, ensure_ascii=False) + "\n")

        logger.info("local_json.delete", count=len(ids))

    def _read_documents(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []

        documents: list[dict[str, Any]] = []
        with open(self.path, "r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    documents.append(json.loads(line))
                except json.JSONDecodeError as error:
                    logger.warning("local_json.bad_document", error=str(error))
        return documents

class PgVectorStore(BaseVectorStore):
    """pgvector — векторное расширение PostgreSQL."""

    def __init__(self, connection_url: Optional[str] = None) -> None:
        settings = get_settings()
        self.connection_url = connection_url or settings.database_url
        self._engine = None

    async def _get_engine(self):
        """Ленивая инициализация SQLAlchemy engine."""
        if self._engine is None:
            from sqlalchemy.ext.asyncio import create_async_engine

            url = self.connection_url.replace(
                "postgresql+psycopg2", "postgresql+asyncpg"
            )
            self._engine = create_async_engine(url)
        return self._engine

    async def upsert(self, documents: list[dict[str, Any]]) -> None:
        """Добавить документы в pgvector."""
        # TODO: реализовать через SQLAlchemy + pgvector
        logger.info("pgvector.upsert", count=len(documents))

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Поиск через cosine similarity в pgvector."""
        # TODO: реализовать embedding + SELECT ... ORDER BY embedding <=> query_embedding
        logger.info("pgvector.search", query=query[:100], top_k=top_k)
        return []

    async def delete(self, ids: list[str]) -> None:
        """Удалить документы."""
        logger.info("pgvector.delete", count=len(ids))

class PineconeStore(BaseVectorStore):
    """Pinecone — облачный векторный стор."""

    def __init__(
        self,
        api_key: str = "",
        index_name: str = "ai-office",
        environment: str = "us-east-1",
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.pinecone_api_key
        self.index_name = index_name or settings.pinecone_index
        self.environment = environment or settings.pinecone_env
        self._index = None

    async def _get_index(self):
        """Ленивая инициализация Pinecone index."""
        if self._index is None:
            from pinecone import Pinecone

            pc = Pinecone(api_key=self.api_key)
            self._index = pc.Index(self.index_name)
        return self._index

    async def upsert(self, documents: list[dict[str, Any]]) -> None:
        """Добавить документы в Pinecone."""
        logger.info("pinecone.upsert", count=len(documents), index=self.index_name)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Поиск через Pinecone query."""
        logger.info("pinecone.search", query=query[:100], top_k=top_k)
        return []

    async def delete(self, ids: list[str]) -> None:
        """Удалить документы."""
        logger.info("pinecone.delete", count=len(ids))

def create_vector_store(
    backend: str = "pgvector",
) -> BaseVectorStore:
    """Фабрика векторных сторов.

    Args:
        backend: 'local_json', 'pgvector' или 'pinecone'.

    Returns:
        Инициализированный векторный стор.
    """
    if backend == "local_json":
        return LocalJsonVectorStore()
    elif backend == "pgvector":
        return PgVectorStore()
    elif backend == "pinecone":
        return PineconeStore()
    else:
        raise ValueError(f"Unknown vector store backend: {backend}")


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_]{3,}", str(text).lower())
        if token
    }


def _score_document(document: dict[str, Any], query_tokens: set[str]) -> int:
    document_tokens = _tokens(document.get("content", ""))
    return len(query_tokens.intersection(document_tokens))


def _matches_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        actual = metadata.get(key)
        if isinstance(expected, dict) and "$in" in expected:
            if actual not in expected["$in"]:
                return False
        elif actual != expected:
            return False
    return True
