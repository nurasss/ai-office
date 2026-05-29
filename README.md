# AI Office — личный автономный AI office

Мультиагентная FastAPI-система из 7 ИИ-сотрудников с Telegram-интерфейсом, RAG/knowledge-слоем и первым autonomous runtime. Текущий уровень: личный 24/7 MVP/autonomous core, а не enterprise worker-платформа.

## Архитектура

```
Telegram / Web / API
  -> PMO / agent routing
  -> Task Engine
  -> SQLAlchemy DB (PostgreSQL or local SQLite)
  -> Autonomous scheduler
  -> Safe action policy + approvals
```

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Заполнить Telegram webhook secret, whitelist и LLM keys
alembic upgrade head
python run.py
```

Проверка:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/autonomous/status
```

## Агенты

PMO, Developer, DataAnalyst, Copywriter, Support, Strategist и Accountant. Модели берутся из `config/settings.yaml` и env, поэтому код не привязан жестко к одному провайдеру.

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

Новый слой хранит `projects`, `tasks`, `task_events`, `agent_runs`, `approvals`, `memories` и `tool_runs` в базе. Локально используется `sqlite:///data/ai_office.db`; для 24/7 лучше PostgreSQL через `DATABASE_URL`.

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
  http://localhost:8000/api/projects \
  -d '{"slug":"ai-office","name":"AI Office","goal":"24/7 autonomous core"}'
curl -X POST http://localhost:8000/api/autonomy/daily-plan
```

Telegram-команды: `/tasks`, `/tasks today`, `/projects`, `/project ai-office`, `/plan`, `/approve <id>`, `/reject <id>`, `/autonomy status`, `/autonomy on`, `/autonomy off`.

Автоматически разрешены read-only проверки, планирование, task/status updates, draft results и подготовка patch/prompt. Deploy, push/merge, удаление файлов, env/secrets, CRM/email/money actions и произвольные shell-команды требуют approval. Pending approvals истекают по `AI_OFFICE_APPROVAL_TTL_HOURS`; stuck/failed задачи ограничены retry budget через `AI_OFFICE_TASK_MAX_RETRIES`.

Подробнее: `docs/AUTONOMOUS_RUNTIME.md`, `docs/SECURITY.md`, `docs/TELEGRAM_COMMANDS.md`.

## Тесты

```bash
python -m pytest -q
ruff check .
```
