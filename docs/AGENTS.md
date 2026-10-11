# Agents

- PMO: planning, routing, quality checks. Enabled by default.
- Support: user/helpdesk answers with scoped RAG. Enabled by default.
- Developer: GitHub/code tasks through safe tools. Enabled by default.
- DataAnalyst: analysis and read-only SQL. Enabled by default.
- Copywriter: drafts and content. Optional.
- Strategist: long-form strategy work. Disabled by default.
- Accountant: document review/draft reconciliation only. Disabled by default.

Feature flags live in `.env.example` as `ENABLE_*_AGENT`.
