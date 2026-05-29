# AI Office basic user manual

> Parsed source metadata
>
> - Owner: `support`
> - Source id: `user_manuals`
> - Source file: `data/raw_knowledge/support/user_manuals/local__basic_user_manual.md`
> - Source format: `md`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# AI Office basic user manual

## Send a task

Use PMO as the default entry point. Write the task in normal language and add
the expected output format when you know it.

Good request:

```text
Prepare a short Telegram post about the AI Office pilot. Use a calm business
tone and mark any facts that need verification.
```

## Use a direct agent

Direct agent mode is useful when the owner is obvious:

- Copywriter for content.
- Developer for code and API.
- Data Analyst for metrics and SQL.
- Support for user questions.
- Strategist for market research.
- Accountant for invoices and finance checks.

## Use route-only mode

Use route-only mode to check routing and RAG hits without spending model tokens.

## Add knowledge

1. Put source files into the matching `knowledge/<agent>/<source>/` folder.
2. Keep files in Markdown, TXT, YAML, JSON or CSV.
3. Run:

```bash
python3 scripts/ingest_knowledge.py --agent all --include-common --dry-run
python3 scripts/ingest_knowledge.py --agent all --include-common
```

## When to ask for help

Ask a human owner when:

- the agent says `needs_review`;
- required source files are absent;
- a customer-facing or finance decision is involved;
- the output includes unsupported facts.
