"""Retriever — RAG-поиск по изолированным базам знаний агентов."""

from typing import Any, Optional

from core.config import load_agent_config
from core.logger import get_logger
from rag.namespaces import get_agent_profile
from rag.vector_store import BaseVectorStore, create_vector_store

logger = get_logger("rag.retriever")

class Retriever:
    """RAG-ретривер: поиск релевантных документов для контекста агентов."""

    def __init__(
        self,
        vector_store: Optional[BaseVectorStore] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        config = load_agent_config().get("rag", {})
        backend = config.get("vector_store", "pgvector")
        self._store = vector_store or create_vector_store(backend)
        self._top_k = config.get("top_k", 5)
        self._chunk_size = config.get("chunk_size", 1024)
        self._agent_id = agent_id
        self._enforce_namespaces = config.get("enforce_agent_namespaces", True)

    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[dict[str, Any]] = None,
        *,
        agent_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Найти релевантные документы.

        Args:
            query: поисковый запрос.
            top_k: число результатов (по умолчанию из конфига).
            filters: фильтры по метаданным (source, date, etc.).
            agent_id: агент, для которого нужно применить namespace-изоляцию.

        Returns:
            Список документов с score и content.
        """
        k = top_k or self._top_k
        effective_agent_id = agent_id or self._agent_id
        scoped_filters = self._scope_filters(
            filters=filters,
            agent_id=effective_agent_id,
        )

        logger.info(
            "retriever.retrieve",
            query=query[:100],
            top_k=k,
            agent_id=effective_agent_id,
            filters=scoped_filters,
        )
        return await self._store.search(query, top_k=k, filters=scoped_filters)

    async def index_documents(
        self,
        documents: list[dict[str, Any]],
        *,
        agent_id: Optional[str] = None,
        namespace: Optional[str] = None,
    ) -> None:
        """Проиндексировать документы.

        Args:
            documents: список dict с ключами content, metadata.
            agent_id: агент-владелец базы знаний.
            namespace: явный namespace, если документ общий или служебный.
        """
        effective_agent_id = agent_id or self._agent_id
        scoped_documents = self._scope_documents(
            documents=documents,
            agent_id=effective_agent_id,
            namespace=namespace,
        )

        logger.info(
            "retriever.index",
            count=len(scoped_documents),
            agent_id=effective_agent_id,
            namespace=namespace,
        )
        await self._store.upsert(scoped_documents)

    def _scope_filters(
        self,
        *,
        filters: Optional[dict[str, Any]],
        agent_id: Optional[str],
    ) -> Optional[dict[str, Any]]:
        """Add a namespace allow-list to retrieval filters."""
        if not self._enforce_namespaces or not agent_id:
            return filters

        profile = get_agent_profile(agent_id)
        allowed = profile["allowed_namespaces"]
        scoped_filters = dict(filters or {})

        requested_namespace = scoped_filters.get("namespace")
        if requested_namespace:
            requested = self._normalize_requested_namespaces(requested_namespace)
            allowed = [namespace for namespace in requested if namespace in allowed]

        scoped_filters["namespace"] = {"$in": allowed}
        scoped_filters["agent_id"] = {"$in": [agent_id, "common"]}
        return scoped_filters

    def _scope_documents(
        self,
        *,
        documents: list[dict[str, Any]],
        agent_id: Optional[str],
        namespace: Optional[str],
    ) -> list[dict[str, Any]]:
        """Attach namespace metadata before documents enter a vector DB."""
        if not agent_id and not namespace:
            return documents

        scoped_documents: list[dict[str, Any]] = []
        for document in documents:
            metadata = dict(document.get("metadata") or {})
            if namespace:
                metadata.setdefault("namespace", namespace)
            elif agent_id:
                metadata.setdefault("namespace", get_agent_profile(agent_id)["namespace"])

            if agent_id:
                metadata.setdefault("agent_id", agent_id)

            scoped_document = dict(document)
            scoped_document["metadata"] = metadata
            scoped_documents.append(scoped_document)

        return scoped_documents

    @staticmethod
    def _normalize_requested_namespaces(value: Any) -> list[str]:
        """Normalize supported namespace filter shapes to a plain list."""
        if isinstance(value, dict) and "$in" in value:
            value = value["$in"]
        if isinstance(value, (list, tuple, set)):
            return [str(namespace) for namespace in value]
        return [str(value)]
