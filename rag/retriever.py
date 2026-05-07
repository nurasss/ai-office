"""Retriever — RAG-поиск по базе знаний офиса."""

from typing import Any, Optional

from core.config import load_agent_config
from core.logger import get_logger
from rag.vector_store import BaseVectorStore, create_vector_store

logger = get_logger("rag.retriever")

class Retriever:
    """RAG-ретривер: поиск релевантных документов для контекста агентов."""

    def __init__(self, vector_store: Optional[BaseVectorStore] = None) -> None:
        config = load_agent_config().get("rag", {})
        backend = config.get("vector_store", "pgvector")
        self._store = vector_store or create_vector_store(backend)
        self._top_k = config.get("top_k", 5)
        self._chunk_size = config.get("chunk_size", 1024)

    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Найти релевантные документы.

        Args:
            query: поисковый запрос.
            top_k: число результатов (по умолчанию из конфига).
            filters: фильтры по метаданным (source, date, etc.).

        Returns:
            Список документов с score и content.
        """
        k = top_k or self._top_k
        logger.info("retriever.retrieve", query=query[:100], top_k=k)
        return await self._store.search(query, top_k=k, filters=filters)

    async def index_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> None:
        """Проиндексировать документы.

        Args:
            documents: список dict с ключами content, metadata.
        """
        logger.info("retriever.index", count=len(documents))
        await self._store.upsert(documents)
