# AI Office — личный автономный AI office

Мультиагентная FastAPI-система из 7 ИИ-сотрудников с Telegram-интерфейсом, RAG/knowledge-слоем, goal engine и demo-product surface: dashboard, memory, generated sites и interactive tools.

## Архитектура

```
Telegram / Web / API
  -> PMO / agent routing
  -> Goal engine / memory
  -> Task Engine
  -> SQLAlchemy DB (PostgreSQL or local SQLite)
  -> Worker
  -> ToolAdapter + approvals
  -> Audit / model usage
  -> Autonomous scheduler
  -> Safe action policy + approvals
```

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d postgres redis
alembic upgrade head
python run.py
```

В отдельном терминале:

```bash
python -m workers.runner
```

Redis/RQ worker для controlled pilot:

```bash
python -m workers.rq_worker
```

Проверка:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/api/autonomous/status
```

Без API-ключей проект работает в fake/dry-run mode: модели deterministic, GitHub write создает dry-run + approval, Telegram без токена просто пропускает отправку.

## Controlled Pilot Production Package

Production readiness is guarded by explicit scripts and fail-fast startup checks:

```bash
ruff check .
python scripts/check_no_secrets.py
python scripts/production_preflight.py
python scripts/check_migrations.py
./scripts/make_release_archive.sh
python scripts/check_no_secrets.py dist/ai-office-release.zip
```

Use `.env.example` for local development and `.env.production.example` for
VPS/staging/prod. In `ENVIRONMENT=production`, startup rejects placeholder
API/admin/cron secrets, SQLite, missing Redis, fake model/embedding providers,
wildcard CORS, missing Telegram allowlists, and unsafe real-tool/autonomy
combinations.

VPS staging:

```bash
POSTGRES_PASSWORD=change-me \
AI_OFFICE_API_KEY=change-me \
AI_OFFICE_ADMIN_TOKEN=change-me-admin \
CRON_SECRET=change-me-cron \
TELEGRAM_WEBHOOK_SECRET=change-me-webhook \
docker compose -f docker-compose.prod.yml up -d --build postgres redis migrate api worker scheduler
```

Admin/dashboard pages require `Authorization: Bearer <AI_OFFICE_ADMIN_TOKEN>`.
Public API clients use `X-API-Key: <AI_OFFICE_API_KEY>` when
`AI_OFFICE_REQUIRE_API_KEY=true`.

Runbooks: `docs/PRODUCTION_READINESS.md`, `docs/STAGING_RUNBOOK.md`,
`docs/OPERATIONS_RUNBOOK.md`, `docs/SECURITY.md`, `docs/TOOLS.md`, and
`docs/PILOT_LAUNCH_CHECKLIST.md`.

## P2 Demo Product

P2 добавляет продуктовый слой поверх pilot runtime:

- Telegram Product Bot: чат, product-команды, inline approvals
- Goal Engine: `/add_goal`, `/goals`, `/daily_plan`
- Memory: пользователь, проект, стиль общения, важные факты
- Generated sites: `/sites/{site_id}`
- Generated tools: `/tools/{tool_id}`
- Demo pages: `/dashboard`, `/agents`, `/goals`, `/tasks`, `/sites`, `/tools`, `/memory`, `/landing`
- Separate compose stack: `docker-compose.prod.yml`
- Demo seed: `uv run python scripts/seed_demo.py`

Ключевые Telegram-команды:

```text
/status
/add_goal
/goals
/tasks
/daily_plan
/memory
/create_site
/create_tool
/brain_status
/approve <id>
/reject <id>
```

Поддерживаются и естественные запросы:

```text
запомни: мой главный проект сейчас AI Office
что ты обо мне помнишь?
что ты знаешь про мой проект?
создай сайт для AI Office
создай калькулятор стоимости AI Office
создай GitHub issue с задачами на завтра
```

## Агенты

PMO, Developer, DataAnalyst, Copywriter, Support, Strategist и Accountant. В production-pilot по умолчанию активны PMO, Support, Developer и DataAnalyst; Strategist и Accountant отключены feature flags.

Агенты могут получать read-only публичный web-контекст для актуальных задач
(`latest`, `сегодня`, новости, цены, docs, release notes, рынок, законы), если
включено:

```text
AI_OFFICE_WEB_ACCESS_ENABLED=true
```

Web access не дает агентам право логиниться, отправлять формы, покупать,
деплоить или делать write-действия. Это только поиск/чтение публичных страниц.

## Структура проекта

```
ai_office/
├── agents/          # Классы агентов
├── api/             # Product API и autonomous runtime API
├── core/            # Auth, DB, модели, schemas, LLM router, config
├── services/        # Projects/tasks/approvals/autonomy/tools services
├── workers/         # DB-backed worker runner
├── models/          # Pilot model router + fake provider
├── security/        # PII redaction and prompt-injection guard
├── prompts/         # System prompts (YAML)
├── tools/           # MCP-инструменты (Slack, Jira, GitHub, ERP)
├── rag/             # Векторная БД (pgvector / Pinecone)
├── knowledge/       # Исходные документы для изолированных RAG namespaces
├── memory/          # Long-term memory store
├── scripts/         # Служебные команды, включая ingest_knowledge.py
├── orchestrator.py  # LangGraph StateGraph
├── config/          # Настройки (YAML)
└── requirements.txt
```

## Обучение агентов

Источники знаний описаны в `config/knowledge_sources.yaml`. Каждый агент индексируется в отдельный namespace, а общая корпоративная память хранится отдельно в `common_corporate`.

```bash
python3 scripts/ingest_knowledge.py --agent all --include-common --dry-run
python3 scripts/ingest_knowledge.py --agent pmo --include-common
```

Подробная программа обучения: `docs/AGENT_TRAINING_PLAN.md`.

Для локального smoke-прогона без Postgres используется `local_json` backend:

```bash
python3 scripts/ingest_knowledge.py --agent all --include-common
python3 scripts/smoke_first_task.py
```

Если API-ключи еще не настроены, можно проверить только маршрутизацию и RAG:

```bash
python3 scripts/smoke_first_task.py --route-only
```

## Product API

В личном режиме `AI_OFFICE_REQUIRE_API_KEY=false`, поэтому `X-API-Key` не нужен:

```bash
curl -X POST http://localhost:8000/api/office/tasks \
  -H "Content-Type: application/json" \
  -d '{"task":"Напиши короткий пост о запуске ИИ-офиса","agent_id":"pmo"}'
```

Для публичного сервера можно включить `AI_OFFICE_REQUIRE_API_KEY=true` и
передавать `X-API-Key: <AI_OFFICE_API_KEY>`.

Проверить только маршрут и RAG без LLM-вызова:

```bash
curl -X POST http://localhost:8000/api/office/tasks \
  -H "Content-Type: application/json" \
  -d '{"task":"Напиши короткий пост о запуске ИИ-офиса","route_only":true}'
```

## Autonomous Runtime

Новый слой хранит `workspaces`, `tasks`, `task_runs`, `agent_runs`, `tool_calls`, `approvals`, `audit_events`, `knowledge_documents`, `knowledge_chunks`, `model_usage`, legacy `projects/task_events/tool_runs` и memory tables. Локально можно использовать SQLite fallback, но `.env.example` настроен на Postgres + Redis через `docker compose`.

Для persistent deployment используйте Alembic:

```bash
alembic upgrade head
```

`init_db()` остается fallback-ом для локальных smoke-прогонов и тестов. Новую миграцию позже можно создать так:

```bash
alembic revision --autogenerate -m "describe_change"
alembic upgrade head
```

Основные endpoints:

```bash
curl http://localhost:8000/api/projects
curl -X POST -H "Content-Type: application/json" \
  http://localhost:8000/api/tasks \
  -d '{"title":"Pilot task","input_text":"Проанализируй запрос клиента","agent_hint":"pmo","workspace_id":"default"}'
curl http://localhost:8000/api/tasks
curl http://localhost:8000/api/approvals
curl http://localhost:8000/api/audit
curl http://localhost:8000/api/metrics/summary
curl -X POST -H "Content-Type: application/json" \
  http://localhost:8000/api/knowledge/upload \
  -d '{"agent_namespace":"agent_support","title":"GitHub setup","content":"GitHub integration setup uses token placeholders."}'
curl "http://localhost:8000/api/knowledge/search?query=GitHub&agent_namespace=agent_support"
curl -X POST -H "Content-Type: application/json" \
  http://localhost:8000/api/projects \
  -d '{"slug":"ai-office","name":"AI Office","goal":"24/7 autonomous core"}'
curl -X POST http://localhost:8000/api/autonomy/daily-plan
```

Telegram-команды: `/status`, `/add_goal`, `/goals`, `/daily_plan`, `/memory`, `/create_site`, `/create_tool`, `/brain_status`, `/tasks`, `/tasks today`, `/projects`, `/project ai-office`, `/plan`, `/approve <id>`, `/reject <id>`, `/autonomy status`, `/autonomy on`, `/autonomy off`.

Автоматически разрешены read-only проверки, планирование, task/status updates, draft results и подготовка patch/prompt. Deploy, push/merge, удаление файлов, env/secrets, CRM/email/money actions и произвольные shell-команды требуют approval. Pending approvals истекают по `AI_OFFICE_APPROVAL_TTL_HOURS`; stuck/failed задачи ограничены retry budget через `AI_OFFICE_TASK_MAX_RETRIES`.

Tool policy:

- Safe read/draft runs immediately.
- GitHub write, Telegram send, financial actions and destructive tools require approval.
- SQL tool is read-only and rejects write/multiple-statement queries.
- PII redaction runs before pilot model calls; prompt-injection findings are audited.

Admin pilot pages:

- `/admin/tasks`
- `/admin/approvals`
- `/admin/audit`
- `/admin/costs`
- `/admin/knowledge`

P2 product pages:

- `/dashboard`
- `/agents`
- `/goals`
- `/tasks`
- `/sites`
- `/tools`
- `/memory`
- `/landing`

Evals:

```bash
python -m evals.runner
```

Smoke test against a running local app:

```bash
bash scripts/pilot_smoke_test.sh
```

24/7 demo/prod-style local run:

```bash
docker compose -f docker-compose.prod.yml up -d
uv run alembic upgrade head
uv run python scripts/seed_demo.py
```

Demo walkthrough: `DEMO_SCRIPT.md`

Подробнее: `docs/OPERATIONS_RUNBOOK.md`, `docs/AUTONOMOUS_RUNTIME.md`, `docs/SECURITY.md`, `SECURITY.md`, `docs/TELEGRAM_COMMANDS.md`.

## Тесты

```bash
python -m pytest -q
ruff check .
```
