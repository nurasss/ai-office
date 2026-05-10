"""RAG (Retrieval-Augmented Generation) — векторная БД и namespace policy."""

from rag.namespaces import get_agent_profile, load_knowledge_catalog
from rag.retriever import Retriever
from rag.vector_store import BaseVectorStore, LocalJsonVectorStore, create_vector_store

__all__ = [
    "BaseVectorStore",
    "LocalJsonVectorStore",
    "Retriever",
    "create_vector_store",
    "get_agent_profile",
    "load_knowledge_catalog",
]
