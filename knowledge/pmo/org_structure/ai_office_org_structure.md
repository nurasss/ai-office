# AI Office organizational structure

## Top-level flow

CEO or user sends every task through PMO. PMO is the only default entry point
for multi-agent execution.

```text
CEO/User
  -> PMO
      -> Data Analyst
      -> Developer
      -> Copywriter
      -> Support
      -> Strategist
      -> Accountant
```

## Responsibility model

| Role | Responsibility | Escalates to |
|---|---|---|
| PMO | Routing, decomposition, deadlines, dependencies | Human owner |
| Copywriter | Content drafts and editorial adaptation | PMO for missing facts |
| Data Analyst | Data requests, SQL, metrics, reports | PMO for missing data |
| Developer | Code, API, architecture, review | PMO for unclear scope |
| Support | FAQ, troubleshooting, client answers | L2 or human support |
| Strategist | Market, roadmap, competitor analysis | PMO for missing sources |
| Accountant | Invoices, acts, contracts, taxes | Human finance reviewer |

## Human review

All outputs are drafts or verified checks for a responsible employee. Final
publication, deployment, customer-facing response and financial approval remain
human-controlled unless a separate production approval process is configured.

