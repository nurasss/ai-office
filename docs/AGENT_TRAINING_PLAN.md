# Программа обучения AI Office

Документ описывает, какие знания загружать в RAG каждого ИИ-сотрудника и какие правила изоляции соблюдать при пилоте.

## Техническая схема

1. **Изолированные RAG namespaces.** Каждый агент получает свой namespace: `agent_pmo`, `agent_copywriter`, `agent_developer`, `agent_support`, `agent_data_analyst`, `agent_accountant`, `agent_strategist`. Общие сведения компании хранятся отдельно в `common_corporate`.
2. **Загрузка источников.** Каталог источников описан в [config/knowledge_sources.yaml](../config/knowledge_sources.yaml). Файлы кладутся в `knowledge/<agent>/...` и `knowledge/common/...`, затем индексируются через `scripts/ingest_knowledge.py`.
3. **Долгосрочная память.** Успешные решения и инциденты сохраняются в `data/memory/*.jsonl`. Папка `data/` игнорируется Git, поэтому runtime-память не попадает в репозиторий.
4. **Общий корпоративный контекст.** Все агенты могут читать только `common_corporate` и собственный namespace. PMO координирует передачу результатов между агентами.
5. **Контроль доступа.** Финансовые, технические, support и маркетинговые материалы не смешиваются. Cross-agent контекст передается только явно через состояние оркестратора.
6. **Лимит контекста.** По умолчанию агент получает до 3 RAG-чанков и до 2 событий памяти; JSONL-память хранит ограниченный хвост событий на агента.

## Команды

Проверить, какие файлы будут загружены:

```bash
python3 scripts/ingest_knowledge.py --agent all --include-common --dry-run
```

Загрузить общие документы и документы конкретного агента:

```bash
python3 scripts/ingest_knowledge.py --agent pmo --include-common
python3 scripts/ingest_knowledge.py --agent copywriter
python3 scripts/ingest_knowledge.py --agent developer
```

## Состав знаний по агентам

| Агент | Namespace | Что загружать |
|---|---|---|
| PMO | `agent_pmo` | Структура отделов, регламенты бизнес-процессов, карта ролей AI Office, SMART-шаблоны, SLA и правила контроля качества |
| Copywriter | `agent_copywriter` | Брендбук, tone of voice, 20-50 лучших постов/рассылок/статей, глоссарий терминов и продуктов |
| Developer | `agent_developer` | Style guides, архитектурные схемы, API/Swagger, исторические PR и решения code review |
| Support | `agent_support` | FAQ, successful tickets, user manuals, troubleshooting trees, правила L1/L2 эскалации |
| Data Analyst | `agent_data_analyst` | Data dictionaries, формулы KPI, SQL-паттерны, примеры аналитических отчетов и дашбордов |
| Accountant | `agent_accountant` | Шаблоны инвойсов/договоров/актов, учетная политика, налоговые ставки, матрица допусков |
| Strategist | `agent_strategist` | OKR, market research, competitor dossiers, прошлые бизнес-планы и финмодели |

## Правила качества

- PMO обязан возвращать задачу агенту, если итог не соответствует формату или SLA.
- Copywriter не получает доступ к техническим и финансовым источникам.
- Developer использует code-review checklist и отмечает security-риск отдельно.
- Support эскалирует на L2 при уверенности ниже `0.7`.
- Data Analyst не выдумывает метрики и всегда указывает источник данных.
- Accountant работает в режиме zero-hallucination: если данных нет, статус `needs_review`.
- Strategist разделяет факты, интерпретации и ограничения анализа.

## Итеративное обучение

После каждого исправления человеком желательно записывать инцидент в long-term memory:

```python
from memory import LongTermMemoryStore

memory = LongTermMemoryStore()
memory.record_incident(
    agent_id="pmo",
    task="Пользователь попросил подготовить пост по итогам анализа рынка",
    lesson="Сначала маршрутизировать исследование Strategist, затем передавать выводы Copywriter.",
    outcome="Маршрутизация исправлена человеком",
)
```

Эта запись попадет в память PMO. Инциденты, полезные всем агентам, можно писать в `common_incidents`; они все равно остаются отдельными от RAG namespaces.
