# Codex Delivery Report

## 1. Что было найдено в проекте

- FastAPI backend with Jinja web UI and Telegram/webhook flows.
- Existing SQLAlchemy/Alembic autonomous core for projects, tasks, events, approvals and tool runs.
- Existing RAG namespace filtering with local JSON fallback.
- Existing direct/stub external tools for GitHub/Telegram/SQL, without one ToolAdapter contract.
- Existing tests were already broad; the new work kept legacy behavior compatible.

## 2. Какие проблемы были исправлены

- Added P0 production-pilot schema for workspaces, task runs, tool calls, audit events, knowledge documents/chunks and model usage.
- Added DB-backed worker execution with fake deterministic model path.
- Added ToolAdapter contract, tool policy, registry and safe P0 tools.
- Added approval creation for dangerous/write/send/destructive tools.
- Added audit logging with secret/PII redaction.
- Added prompt-injection detection and untrusted-context wrapping.
- Added PII redaction before pilot model calls.
- Added `/ready`, task run/audit endpoints, approval detail endpoint, metrics/cost endpoints.
- Updated repo cleanup, env example, local Postgres/Redis compose, docs and CI.

## 3. Какие файлы изменены

- Updated: `.env.example`, `.gitignore`, `README.md`, `api/autonomous.py`, `core/auth.py`, `core/config.py`, `core/db.py`, `core/models.py`, `core/schemas.py`, `core/task_lifecycle.py`, `services/approval_service.py`, `services/task_service.py`, `web/app.py`.
- Added: `IMPLEMENTATION_PLAN.md`, `SECURITY.md`, `docker-compose.yml`, `.github/workflows/ci.yml`, new docs, migration, worker/model/security/tool modules and focused tests.

## 4. Какие новые модули добавлены

- `workers/queue.py`, `workers/tasks.py`, `workers/runner.py`
- `models/router.py`, `models/providers/base.py`, `models/providers/fake_provider.py`
- `security/pii.py`, `security/prompt_injection.py`
- `tools/base.py`, `tools/policy.py`, `tools/registry.py`, `tools/fake_tools.py`, `tools/github_tools.py`, `tools/telegram_tools.py`, `tools/sql_tools.py`
- `services/audit_service.py`

## 5. Какие env-переменные нужны

Core: `APP_ENV`, `APP_NAME`, `APP_BASE_URL`, `FRONTEND_BASE_URL`, `DATABASE_URL`, `REDIS_URL`, `VECTOR_BACKEND`, `RAG_DEFAULT_TOP_K`.

Models/tools: `MODEL_PROVIDER_PRIMARY`, `MODEL_PROVIDER_FALLBACK`, `DEFAULT_CHEAP_MODEL`, `DEFAULT_MID_MODEL`, `DEFAULT_STRONG_MODEL`, `ENABLE_REAL_TOOLS`, `ENABLE_APPROVAL_REQUIRED`, `ENABLE_PII_REDACTION`.

Integrations: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`, `TELEGRAM_BOT_TOKEN`, Telegram allowlists.

## 6. Как запустить локально

```bash
cp .env.example .env
docker compose up -d postgres redis
alembic upgrade head
python run.py
```

Worker:

```bash
python -m workers.runner
```

## 7. Как запустить тесты

```bash
uv run pytest -q
```

Result: `114 passed, 4 warnings`.

## 8. Какие интеграции работают реально

- Telegram helper keeps the existing real-send path when token/chat config exists.
- Existing legacy LLM router still supports configured OpenAI/Anthropic/Google keys.

## 9. Какие интеграции работают в fake/dry-run mode

- Fake model provider for worker/tests.
- GitHub issue creation dry-run with pending approval.
- Telegram notify tool fake mode when real tools are disabled or token is missing.
- SQL read-only tool runs only safe SELECT/WITH/EXPLAIN.
- Fake draft/destructive tools for policy tests.

## 10. Какие действия требуют approval

- `high_risk_write`
- `external_send`
- `financial_action`
- `delete_or_destructive`
- `low_risk_write` when `ENABLE_APPROVAL_REQUIRED=true`

## 11. Какие ограничения остались

- Worker is a DB-backed local pilot runner, not a Redis Dramatiq/RQ/Celery distributed queue yet.
- GitHub real write execution is intentionally not implemented in P0; dry-run + approval foundation is present.
- pgvector persistence schema exists, while the retriever still uses the local JSON fallback implementation.
- Admin dashboard pages were not expanded beyond backend endpoints/docs.

## 12. Что делать следующим PR

- Replace local worker polling with RQ/Dramatiq over Redis.
- Implement real GitHub read/write clients behind approval.
- Move RAG retrieval to Postgres/pgvector with citations stored from `knowledge_chunks`.
- Add admin approval/cost/audit UI pages.
- Add eval runner cases and trend reports.
