# Knowledge Sources

Эта папка предназначена для исходных документов, которые затем загружаются в изолированные RAG namespaces.

Структура источников задается в `config/knowledge_sources.yaml`.
Папка `data/` используется для runtime-памяти и не является местом для RAG-источников.

Минимальная схема:

```text
knowledge/
  common/
    company_overview/
    ai_office_roles/
    business_processes/
    tone_of_voice/
  pmo/
    org_structure/
    process_regulations/
    sla/
    task_tracker_rules/
    routing_rules/
    smart_templates/
  copywriter/
    brandbook/
    examples/
    glossary/
    pr_templates/
  developer/
    style_guides/
    architecture/
    api_specs/
    pull_requests/
  support/
    faq/
    successful_tickets/
    user_manuals/
    troubleshooting_guides/
    escalation_rules/
  data_analyst/
    data_dictionaries/
    kpi_formulas/
    sql_patterns/
    report_examples/
  accountant/
    document_templates/
    accounting_policy/
    expense_policy/
    legal_entities/
    tax_reference/
    chart_of_accounts/
    approval_matrix/
  strategist/
    okrs/
    roadmaps/
    market_research/
    competitors/
    business_plans/
```

Перед загрузкой можно выполнить dry-run:

```bash
python3 scripts/parse_knowledge_sources.py --init-raw
python3 scripts/parse_knowledge_sources.py --source-plan
python3 scripts/parse_knowledge_sources.py --seed-local
python3 scripts/parse_knowledge_sources.py --agent all --dry-run
python3 scripts/parse_knowledge_sources.py --agent all
python3 scripts/ingest_knowledge.py --agent all --include-common --dry-run
```
