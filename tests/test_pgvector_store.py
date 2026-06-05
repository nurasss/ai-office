import asyncio

from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from rag.pgvector_store import EmbeddingProviderError, create_document, search_chunks
from rag.vector_store import PgVectorStore


class StubEmbeddingProvider:
    provider = "openai"
    model = "text-embedding-3-small"
    dimensions = 3

    def embed_texts(self, texts):
        vectors = []
        for text in texts:
            lowered = text.lower()
            if "github" in lowered:
                vectors.append([1.0, 0.0, 0.0])
            elif "tone" in lowered or "voice" in lowered:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


def test_create_document_stores_embeddings_and_returns_vector_ranked_results(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'pgvector-store.db'}")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    monkeypatch.setattr("rag.pgvector_store.get_embedding_provider", lambda: StubEmbeddingProvider())

    with get_session() as db:
        document, chunks = create_document(
            db,
            workspace_id="default",
            agent_namespace="agent_support",
            title="Support GitHub",
            source_uri="support.md",
            file_type="md",
            content="GitHub token rotation and repository access for support engineers.",
        )
        db.commit()

        assert document.id
        assert chunks
        assert chunks[0].embedding == [1.0, 0.0, 0.0]
        assert chunks[0].embedding_model == "text-embedding-3-small"
        assert chunks[0].embedding_dimensions == 3

        results = search_chunks(
            db,
            query="GitHub repository access",
            workspace_id="default",
            allowed_namespaces=["agent_support"],
            top_k=3,
        )

        assert results
        assert results[0]["source_uri"] == "support.md"
        assert "GitHub token rotation" in results[0]["chunk"]
        assert results[0]["score"] > 0.99


def test_search_chunks_uses_lexical_fallback_only_when_embeddings_are_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'pgvector-fallback.db'}")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()

    def raise_no_embeddings():
        raise EmbeddingProviderError("provider missing")

    monkeypatch.setattr("rag.pgvector_store.get_embedding_provider", raise_no_embeddings)

    with get_session() as db:
        _, chunks = create_document(
            db,
            workspace_id="default",
            agent_namespace="agent_support",
            title="Fallback doc",
            source_uri="fallback.md",
            file_type="md",
            content="GitHub issue triage checklist for support.",
        )
        db.commit()

        assert chunks[0].embedding is None
        assert chunks[0].embedding_model == ""
        assert chunks[0].embedding_dimensions == 0

        results = search_chunks(
            db,
            query="GitHub checklist",
            workspace_id="default",
            allowed_namespaces=["agent_support"],
            top_k=3,
        )

        assert results
        assert results[0]["source_uri"] == "fallback.md"
        assert results[0]["score"] > 0


def test_pgvector_store_upsert_and_search_respects_namespace_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'pgvector-retriever.db'}")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    monkeypatch.setattr("rag.pgvector_store.get_embedding_provider", lambda: StubEmbeddingProvider())

    store = PgVectorStore()
    asyncio.run(
        store.upsert(
            [
                {
                    "id": "dev_1",
                    "content": "GitHub repository conventions for developers",
                    "metadata": {
                        "namespace": "agent_developer",
                        "agent_id": "developer",
                        "source": "knowledge/developer/repo.md",
                        "source_title": "Developer Repo",
                    },
                },
                {
                    "id": "copy_1",
                    "content": "Tone of voice guide for copywriters",
                    "metadata": {
                        "namespace": "agent_copywriter",
                        "agent_id": "copywriter",
                        "source": "knowledge/copywriter/tone.md",
                        "source_title": "Copy Tone",
                    },
                },
            ]
        )
    )

    copy_results = asyncio.run(
        store.search(
            "tone voice",
            filters={
                "namespace": {"$in": ["agent_copywriter"]},
                "agent_id": {"$in": ["copywriter", "common"]},
            },
        )
    )
    developer_results = asyncio.run(
        store.search(
            "tone voice",
            filters={
                "namespace": {"$in": ["agent_developer"]},
                "agent_id": {"$in": ["developer", "common"]},
            },
        )
    )

    assert [result["metadata"]["namespace"] for result in copy_results] == ["agent_copywriter"]
    assert [result["metadata"]["agent_id"] for result in copy_results] == ["copywriter"]
    assert developer_results == []
