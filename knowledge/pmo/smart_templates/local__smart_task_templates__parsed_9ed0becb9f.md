# SMART task templates

> Parsed source metadata
>
> - Owner: `pmo`
> - Source id: `smart_templates`
> - Source file: `data/raw_knowledge/pmo/smart_templates/local__smart_task_templates.md`
> - Source format: `md`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# SMART task templates

## Generic SMART task

```markdown
# Task

## Specific
What exactly must be produced?

## Measurable
How will we know the result is complete?

## Achievable
What source, tool or access is required?

## Relevant
Which business goal does this support?

## Time-bound
When should the first draft or final result be ready?

## Owner
Assigned agent:

## Review
Human reviewer:
```

## Copywriter task

- Output format: post, email, article, landing block or press release.
- Channel: Telegram, LinkedIn, blog, website or internal communication.
- Audience: employees, clients, investors or partners.
- Required facts: list verified inputs from PMO.
- Style: use `agent_copywriter` brandbook only.

## Data Analyst task

- Business question.
- Source tables/files.
- Required metrics and formulas.
- Time period and filters.
- Expected output: SQL, table, chart description or memo.
- Verification: arithmetic check and confidence level.

## Accountant task

- Document type: invoice, act, contract or expense report.
- Legal entity and counterparty.
- Required check: totals, tax, limits, approval matrix.
- Source files.
- Output status: `verified`, `discrepancy` or `needs_review`.
