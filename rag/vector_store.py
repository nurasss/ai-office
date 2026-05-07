"""Vector Store — заглушки под pgvector и Pinecone."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("rag.vector_store")

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
        backend: 'pgvector' или 'pinecone'.

    Returns:
        Инициализированный векторный стор.
    """
    if backend == "pgvector":
        return PgVectorStore()
    elif backend == "pinecone":
        return PineconeStore()
    else:
        raise ValueError(f"Unknown vector store backend: {backend}")
