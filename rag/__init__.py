"""RAG (Retrieval-Augmented Generation) — векторная БД и namespace policy."""

from rag.namespaces import get_agent_profile, load_knowledge_catalog
from rag.retriever import Retriever
from rag.vector_store import BaseVectorStore, create_vector_store

__all__ = [
    "BaseVectorStore",
    "Retriever",
    "create_vector_store",
    "get_agent_profile",
    "load_knowledge_catalog",
]
