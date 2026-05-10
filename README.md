# AI Office — Полностью автономный цифровой ИИ-офис

Мультиагентная система из 7 специализированных ИИ-сотрудников, оркеструемых через LangGraph.

## Архитектура

```
                ┌──────────────┐
                │  CEO / User  │
                └──────┬───────┘
                       │
                ┌──────▼───────┐
                │  PMO_Agent   │  ← Оркестратор (entry point)
                └──────┬───────┘
                       │
        ┌──────┬───────┼───────┬────────┬──────────┐
        ▼      ▼       ▼       ▼        ▼          ▼
   DataAnalyst Dev   Copy   Support  Strategist  Accountant
```

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Вставить реальные API-ключи в .env
```

## Агенты

| Агент | Роль | Модель |
|-------|------|--------|
| PMO_Agent | Оркестратор, декомпозиция задач | Claude Sonnet 4.6 |
| DataAnalyst_Agent | Анализ данных и метрик | GPT-5.5 |
| Developer_Agent | Написание и ревью кода | Claude 4.7 Opus |
| Copywriter_Agent | Контент и тексты | Claude Sonnet 4.6 |
| Support_Agent | Техподдержка (L1→L2 эскалация) | Sonnet 4.6 / Opus 4.7 |
| Strategist_Agent | Анализ рынка, документы | Gemini 3.1 Pro |
| Accountant_Agent | Сверка инвойсов (zero-hallucination) | Sonnet 4.6 / Opus 4.7 |

## Структура проекта

```
ai_office/
├── agents/          # Классы агентов
├── core/            # LLM-роутер, конфиг, state, логгер
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
python scripts/ingest_knowledge.py --agent all --include-common --dry-run
python scripts/ingest_knowledge.py --agent pmo --include-common
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

Основной endpoint для веба, Telegram-бота или Mini App:

```bash
curl -X POST http://localhost:8000/api/office/tasks \
  -H "Content-Type: application/json" \
  -d '{"task":"Напиши короткий пост о запуске ИИ-офиса","agent_id":"pmo"}'
```

Проверить только маршрут и RAG без LLM-вызова:

```bash
curl -X POST http://localhost:8000/api/office/tasks \
  -H "Content-Type: application/json" \
  -d '{"task":"Напиши короткий пост о запуске ИИ-офиса","route_only":true}'
```
