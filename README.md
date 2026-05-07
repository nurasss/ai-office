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
├── orchestrator.py  # LangGraph StateGraph
├── config/          # Настройки (YAML)
└── requirements.txt
```
