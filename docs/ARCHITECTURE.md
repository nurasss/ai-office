# Architecture

AI Office pilot runtime uses FastAPI, SQLAlchemy/Alembic, a DB-backed local worker, isolated RAG namespaces, model routing, ToolAdapter policy, approvals and audit events.

Request flow:

```text
API task -> task row pending -> Redis/RQ or DB fallback queue -> worker -> task_run/agent_run -> model/tool -> audit/model_usage -> result or approval
```

External side effects are disabled by default with `ENABLE_REAL_TOOLS=false`.

P1 adds:

- Redis/RQ queue backend with DB fallback.
- Approved GitHub write execution.
- DB-backed knowledge ingestion/retrieval over `knowledge_documents` and `knowledge_chunks`.
- Minimal admin pages under `/admin/*`.
- Baseline eval runner.
