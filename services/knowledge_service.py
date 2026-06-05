"""Knowledge ingestion and retrieval service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import KnowledgeDocument
from rag.pgvector_store import create_document, search_chunks, upsert_documents
from services.audit_service import audit_log


class KnowledgeService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ingest_text(
        self,
        *,
        workspace_id: str,
        agent_namespace: str,
        title: str,
        source_uri: str,
        file_type: str,
        content: str,
    ) -> dict[str, object]:
        document, chunks = create_document(
            self.db,
            workspace_id=workspace_id,
            agent_namespace=agent_namespace,
            title=title,
            source_uri=source_uri,
            file_type=file_type,
            content=content,
        )
        audit_log(
            self.db,
            workspace_id=workspace_id,
            actor_type="user",
            actor_id="api",
            action="knowledge.document_uploaded",
            object_type="knowledge_document",
            object_id=document.id,
            metadata={"agent_namespace": agent_namespace, "source_uri": source_uri, "chunks": len(chunks)},
        )
        for chunk in chunks:
            audit_log(
                self.db,
                workspace_id=workspace_id,
                actor_type="system",
                actor_id="rag_ingestion",
                action="knowledge.chunk_created",
                object_type="knowledge_chunk",
                object_id=chunk.id,
                metadata={
                    "document_id": document.id,
                    "agent_namespace": agent_namespace,
                    "embedding_model": chunk.embedding_model,
                    "embedding_dimensions": chunk.embedding_dimensions,
                },
            )
        self.db.commit()
        return {"document_id": document.id, "chunks": len(chunks)}

    def upsert_retriever_documents(
        self,
        *,
        documents: list[dict[str, object]],
        workspace_id: str = "default",
    ) -> int:
        created_chunks = upsert_documents(
            self.db,
            documents=documents,
            workspace_id=workspace_id,
        )
        self.db.commit()
        return created_chunks

    def list_documents(
        self,
        *,
        workspace_id: str = "default",
        agent_namespace: str | None = None,
    ) -> list[KnowledgeDocument]:
        stmt = select(KnowledgeDocument).where(KnowledgeDocument.workspace_id == workspace_id).order_by(
            KnowledgeDocument.created_at.desc()
        )
        if agent_namespace:
            stmt = stmt.where(KnowledgeDocument.agent_namespace == agent_namespace)
        return list(self.db.scalars(stmt))

    def search(
        self,
        *,
        query: str,
        agent_namespace: str,
        workspace_id: str = "default",
        top_k: int = 6,
    ) -> list[dict[str, object]]:
        from rag.retrieval import allowed_namespaces_for

        return search_chunks(
            self.db,
            query=query,
            workspace_id=workspace_id,
            allowed_namespaces=allowed_namespaces_for(agent_namespace),
            top_k=top_k,
        )
