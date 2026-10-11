# RAG

RAG namespaces are isolated per agent:

- `agent_pmo`
- `agent_support`
- `agent_developer`
- `agent_analyst`
- `agent_copywriter`
- `agent_strategist`
- `agent_accountant`
- shared/common namespaces from `config/knowledge_sources.yaml`

The local JSON vector store remains a dev fallback for legacy retriever code.

P1 adds DB-backed ingestion/retrieval:

- `POST /api/knowledge/upload`
- `GET /api/knowledge/documents`
- `GET /api/knowledge/search`

Embeddings default to deterministic fake vectors through `EMBEDDING_PROVIDER=fake`, while the storage contract is ready for a real embedding provider.

Retrieved chunks are wrapped as untrusted context and prompt-injection findings are returned/audited.
