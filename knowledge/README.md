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
  pmo/
    org_structure/
    process_regulations/
    routing_rules/
    smart_templates/
  copywriter/
    brandbook/
    examples/
    glossary/
  developer/
    style_guides/
    architecture/
    api_specs/
    pull_requests/
  support/
    faq/
    successful_tickets/
    user_manuals/
    escalation_rules/
  data_analyst/
    data_dictionaries/
    kpi_formulas/
    report_examples/
  accountant/
    document_templates/
    accounting_policy/
    tax_reference/
    approval_matrix/
  strategist/
    okrs/
    market_research/
    competitors/
    business_plans/
```

Перед загрузкой можно выполнить dry-run:

```bash
python scripts/ingest_knowledge.py --agent all --include-common --dry-run
```
