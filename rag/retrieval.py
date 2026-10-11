"""DB-backed RAG retrieval with namespace isolation and untrusted context wrapping."""

from __future__ import annotations

from sqlalchemy.orm import Session

from core.config import get_settings
from security.prompt_injection import detect_prompt_injection, sanitize_retrieved_context
from services.audit_service import audit_log
from services.knowledge_service import KnowledgeService


AGENT_NAMESPACES = {
    "pmo": "agent_pmo",
    "support": "agent_support",
    "developer": "agent_developer",
    "data_analyst": "agent_analyst",
    "analyst": "agent_analyst",
    "copywriter": "agent_copywriter",
    "strategist": "agent_strategist",
    "accountant": "agent_accountant",
}

SHARED_NAMESPACES = {"shared_public", "shared_company", "common_corporate"}


def allowed_namespaces_for(agent_namespace: str) -> list[str]:
    normalized = AGENT_NAMESPACES.get(agent_namespace, agent_namespace)
    return [normalized, *sorted(SHARED_NAMESPACES)]


def retrieve_context(
    db: Session,
    *,
    query: str,
    agent_namespace: str,
    workspace_id: str = "default",
    top_k: int | None = None,
) -> list[dict[str, object]]:
    allowed = allowed_namespaces_for(agent_namespace)
    results = KnowledgeService(db).search(
        query=query,
        agent_namespace=agent_namespace,
        workspace_id=workspace_id,
        top_k=top_k or get_settings().rag_default_top_k,
    )
    sanitized: list[dict[str, object]] = []
    for result in results:
        content = str(result.pop("content", ""))
        findings = detect_prompt_injection(content)
        sanitized_chunk = sanitize_retrieved_context(content)
        sanitized.append(
            {
                **result,
                "content_preview": sanitize_retrieved_context(str(result.get("content_preview", ""))),
                "chunk": sanitized_chunk,
                "prompt_injection_findings": [finding.__dict__ for finding in findings],
            }
        )
    audit_log(
        db,
        workspace_id=workspace_id,
        actor_type="agent",
        actor_id=agent_namespace,
        action="knowledge.search_performed",
        object_type="knowledge_chunk",
        object_id="",
        metadata={"query": query[:200], "allowed_namespaces": allowed, "result_count": len(sanitized)},
        commit=True,
    )
    return sanitized
