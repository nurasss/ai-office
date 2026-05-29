# Safe SQL patterns

> Parsed source metadata
>
> - Owner: `data_analyst`
> - Source id: `sql_patterns`
> - Source file: `data/raw_knowledge/data_analyst/sql_patterns/local__safe_sql_patterns.md`
> - Source format: `md`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# Safe SQL patterns

## Source status

These are generic safety patterns for the AI Office prototype. Replace or extend
with company warehouse standards and dbt docs.

## Query checklist

- State the source table and time period.
- Use explicit column names instead of `select *`.
- Filter by date using the business-approved timezone.
- Check row counts before and after joins.
- Use CTEs for readable multi-step logic.
- Avoid destructive SQL unless a human explicitly approves it.

## Join safety

Before joining tables, verify:

- primary key;
- foreign key;
- expected cardinality;
- duplicate behavior;
- null behavior.

## Missing schema behavior

If table or column definitions are absent, return the required schema list and
do not invent table names.
