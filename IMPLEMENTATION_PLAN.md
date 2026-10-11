# AI Office P0 Implementation Plan

## Current Findings

- Stack: Python 3.11, FastAPI, SQLAlchemy, Alembic, LangGraph/LangChain, local Jinja UI, pytest.
- Existing persistence covers legacy autonomous runtime tables (`projects`, `tasks`, `task_events`, `agent_runs`, `approvals`, `tool_runs`) but misses the explicit production P0 tables and audit trail.
- Existing RAG has namespace filtering and a local JSON fallback, but production persistence/citation models are not represented in the DB schema.
- Existing tools are mostly LangChain stubs or direct helpers; there is no unified `ToolAdapter` contract with policy, dry-run, approval and audit.
- Telegram helper already supports safe no-token behavior and approval buttons. GitHub and SQL tools need safe dry-run/read-only adapters.
- Repo has ignored local artifacts (`logs/`, cache dirs, `.env`, local DB/vector data). `.gitignore` needs to be tightened to match the production hardening prompt.

## P0 Scope

1. Repo cleanup baseline: update `.gitignore`, `.env.example`, `SECURITY.md`, operations runbook.
2. Config: extend `core.config.Settings` with P0 env flags and compatibility aliases.
3. DB/Alembic: add `Workspace`, `TaskRun`, production-compatible `ToolCall`, `AuditEvent`, `KnowledgeDocument`, `KnowledgeChunk`, `ModelUsage` and extend `Task`/`Approval`.
4. Task API: add pilot endpoints for task creation/list/detail/cancel/runs/audit and health/ready checks.
5. Worker: add a simple local queue abstraction and fake worker execution path that records task runs, agent runs, model usage and audit events.
6. ToolAdapter: add base interface, policy, registry, fake tools, GitHub dry-run/write approval foundation, Telegram notify and SQL read-only tool.
7. Approvals/audit: ensure dangerous write/send/delete actions create pending approvals and every decision is audited.
8. Safety: add PII redaction and prompt-injection guard with tests.
9. Docs/tests: update README/runbook/security and add focused P0 pytest coverage.

## Non-Goals For This Pass

- No real production deploy.
- No real destructive external writes.
- No secret values in repository.
- No full frontend rewrite.
