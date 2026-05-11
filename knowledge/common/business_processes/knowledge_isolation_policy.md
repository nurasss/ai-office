# Knowledge isolation policy

## Purpose

This policy prevents agents from mixing unrelated corporate knowledge. The
copywriter must not use code standards as a writing style source, the accountant
must not infer financial rules from support tickets, and the developer must not
copy product claims from marketing examples into architecture decisions.

## Allowed context

Each agent receives:

- common corporate context from `common_corporate`;
- its own namespace from `config/knowledge_sources.yaml`;
- explicit verified input passed by PMO from another agent.

## Forbidden context

Agents must not pull raw documents from another agent namespace. Examples:

- Copywriter cannot access `agent_developer`, `agent_data_analyst` or
  `agent_accountant`.
- Accountant cannot access `agent_copywriter`, `agent_developer` or
  `agent_support`.
- Data Analyst cannot use copywriting references as metric definitions.

## Missing-source behavior

If the required source is absent:

- PMO returns a routing plan with `needs_source`.
- Data Analyst says which table, column or KPI formula is missing.
- Accountant returns `needs_review`.
- Strategist marks the statement as an assumption or asks for a dated source.
- Copywriter may draft text, but must mark facts that need verification.

## Preferred source format

All parsed source files should be normalized to Markdown:

- use clear `#` and `##` headings;
- keep one topic per file;
- preserve source date, owner and original system when known;
- keep tables in Markdown or CSV;
- never paste secrets, personal data or private credentials.

