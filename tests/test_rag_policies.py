import asyncio

from rag.retriever import Retriever
from rag.vector_store import BaseVectorStore, LocalJsonVectorStore


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


def test_local_json_store_persists_and_filters_by_namespace(tmp_path):
    store = LocalJsonVectorStore(path=tmp_path / "documents.jsonl")

    asyncio.run(
        store.upsert(
            [
                {
                    "id": "dev_1",
                    "content": "API style guide for developers",
                    "metadata": {"namespace": "agent_developer"},
                },
                {
                    "id": "copy_1",
                    "content": "Tone of voice for copywriters",
                    "metadata": {"namespace": "agent_copywriter"},
                },
            ]
        )
    )

    results = asyncio.run(
        store.search(
            "tone voice",
            filters={"namespace": {"$in": ["agent_developer"]}},
        )
    )

    assert results == []

    results = asyncio.run(
        store.search(
            "tone voice",
            filters={"namespace": {"$in": ["agent_copywriter"]}},
        )
    )

    assert [result["id"] for result in results] == ["copy_1"]
