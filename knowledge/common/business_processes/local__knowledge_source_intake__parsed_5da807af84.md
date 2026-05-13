# Knowledge Source Intake

> Parsed source metadata
>
> - Owner: `common`
> - Source id: `general_business_processes`
> - Source file: `data/raw_knowledge/common/business_processes/local__KNOWLEDGE_SOURCE_INTAKE.md`
> - Source format: `md`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# Knowledge Source Intake

This checklist maps real company exports to isolated AI Office knowledge
folders. Keep every source in the narrowest matching folder and run ingest after
updates.

## Common Corporate

Folder: `knowledge/common/`

- Company website "About" and product description:
  `company_overview/`
- Onboarding, org principles and shared operating rules:
  `business_processes/`
- Shared role descriptions:
  `ai_office_roles/`
- General tone of voice:
  `tone_of_voice/`

## PMO

Folder: `knowledge/pmo/`

- Scrum/Kanban/team regulations: `process_regulations/`
- SLA and deadline policy: `sla/`
- Jira/Trello workflow exports and label rules: `task_tracker_rules/`
- Competency matrix and routing rules: `routing_rules/`
- SMART task templates: `smart_templates/`

## Copywriter

Folder: `knowledge/copywriter/`

- Brandbook, editorial policy, stop words: `brandbook/`
- Best posts, newsletters, articles and press releases: `examples/`
- Product glossary and naming rules: `glossary/`
- PR templates and announcement structures: `pr_templates/`

## Data Analyst

Folder: `knowledge/data_analyst/`

- DDL from `pg_dump -s`, dbt docs and table descriptions:
  `data_dictionaries/`
- Company-approved KPI formulas: `kpi_formulas/`
- Safe SQL snippets and query conventions: `sql_patterns/`
- Metabase/Tableau dashboard descriptions: `report_examples/`

## Developer

Folder: `knowledge/developer/`

- Architecture docs and diagrams as Markdown: `architecture/`
- Swagger/OpenAPI JSON/YAML: `api_specs/`
- Coding standards and lint rules: `style_guides/`
- Good historical PRs and review decisions: `pull_requests/`

## Support

Folder: `knowledge/support/`

- Help Center FAQ exports: `faq/`
- Closed ticket examples with question and answer: `successful_tickets/`
- User manuals: `user_manuals/`
- Troubleshooting scripts: `troubleshooting_guides/`
- L1/L2 escalation matrix: `escalation_rules/`

## Strategist

Folder: `knowledge/strategist/`

- OKR and strategic goals: `okrs/`
- Product roadmaps: `roadmaps/`
- Market and macro reports with dates: `market_research/`
- Competitor dossiers: `competitors/`
- Business plans and investor materials: `business_plans/`

## Accountant

Folder: `knowledge/accountant/`

- Contract, invoice and act templates: `document_templates/`
- Accounting policy: `accounting_policy/`
- Travel and expense policy: `expense_policy/`
- Legal entity cards and bank details: `legal_entities/`
- Tax rates and effective dates: `tax_reference/`
- Chart of accounts: `chart_of_accounts/`
- Approval thresholds: `approval_matrix/`

## Commands

Prepare raw local exports under `data/raw_knowledge/`. This folder is ignored
by Git and is safe for local-only source drops.

Create the full raw folder scaffold:

```bash
python3 scripts/parse_knowledge_sources.py --init-raw
```

The parser has built-in source recipes based on the AI Office training plan.
Print them:

```bash
python3 scripts/parse_knowledge_sources.py --source-plan
```

Write them into `data/raw_knowledge/SOURCE_PLAN.md`:

```bash
python3 scripts/parse_knowledge_sources.py --write-source-plan
```

After `--init-raw`, every raw source folder also contains `_SOURCE_HINT.md`.
Those hint files explain what to collect, where to get it, and how to export it.
The parser ignores `_SOURCE_HINT.md` during parsing.

Recommended layout:

```text
data/raw_knowledge/
  common/
    company_overview/
    tone_of_voice/
  copywriter/
    brandbook/
    examples/
  data_analyst/
    data_dictionaries/
    kpi_formulas/
  developer/
    architecture/
    api_specs/
  support/
    faq/
    troubleshooting_guides/
  strategist/
    roadmaps/
    competitors/
  accountant/
    expense_policy/
    legal_entities/
```

List parser targets:

```bash
python3 scripts/parse_knowledge_sources.py --list-targets
```

Parse one agent:

```bash
python3 scripts/parse_knowledge_sources.py --agent copywriter --dry-run
python3 scripts/parse_knowledge_sources.py --agent copywriter
```

Parse a custom local export folder:

```bash
python3 scripts/parse_knowledge_sources.py --agent support --input ~/Downloads/zendesk-export
```

Force files into one source bucket when the folder name is ambiguous:

```bash
python3 scripts/parse_knowledge_sources.py --agent accountant \
  --input ~/Downloads/finance-docs \
  --source expense_policy
```

Parse everything and then run ingest:

```bash
python3 scripts/parse_knowledge_sources.py --agent all --ingest
```

If no new raw files were parsed, `--ingest` is skipped. To reindex existing
`knowledge/` files anyway, run:

```bash
python3 scripts/parse_knowledge_sources.py --agent all --ingest --force-ingest
```

The parser supports `.md`, `.txt`, `.csv`, `.json`, `.jsonl`, `.yaml`, `.yml`,
`.sql`, `.html`, `.htm`, `.pdf`, `.docx`, `.pptx`, and `.xlsx`. Excel parsing
may require `openpyxl` installed locally.

Manual ingest commands:

```bash
python3 scripts/ingest_knowledge.py --agent all --include-common --dry-run
python3 scripts/ingest_knowledge.py --agent all --include-common
```

## Safety

- Do not put secrets into knowledge files.
- Remove personal data unless the agent explicitly needs it and access is
  approved.
- Prefer Markdown, TXT, YAML, JSON and CSV.
- Include source date and owner when known.
- If the source is missing, create a requirements file rather than inventing
  policy details.
