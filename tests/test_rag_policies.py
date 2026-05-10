import asyncio

from rag.retriever import Retriever
from rag.vector_store import BaseVectorStore


class FakeVectorStore(BaseVectorStore):
    def __init__(self) -> None:
        self.last_search_filters = None
        self.upserted_documents = []

    async def upsert(self, documents):
        self.upserted_documents = documents

    async def search(self, query, top_k=5, filters=None):
        self.last_search_filters = filters
        return []

    async def delete(self, ids):
        return None


def test_retriever_scopes_search_to_agent_and_common_namespaces():
    store = FakeVectorStore()
    retriever = Retriever(vector_store=store, agent_id="developer")

    asyncio.run(retriever.retrieve("api style guide"))

    assert store.last_search_filters["namespace"] == {
        "$in": ["common_corporate", "agent_developer"]
    }
    assert store.last_search_filters["agent_id"] == {
        "$in": ["developer", "common"]
    }


def test_retriever_blocks_requested_foreign_namespace():
    store = FakeVectorStore()
    retriever = Retriever(vector_store=store, agent_id="developer")

    asyncio.run(
        retriever.retrieve(
            "brand voice",
            filters={"namespace": "agent_copywriter"},
        )
    )

    assert store.last_search_filters["namespace"] == {"$in": []}
    assert store.last_search_filters["agent_id"] == {
        "$in": ["developer", "common"]
    }


def test_retriever_indexes_documents_into_owner_namespace():
    store = FakeVectorStore()
    retriever = Retriever(vector_store=store)

    asyncio.run(
        retriever.index_documents(
            [{"content": "tone of voice", "metadata": {}}],
            agent_id="copywriter",
        )
    )

    assert store.upserted_documents[0]["metadata"]["namespace"] == "agent_copywriter"
    assert store.upserted_documents[0]["metadata"]["agent_id"] == "copywriter"
