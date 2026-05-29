# Agent competency matrix

## Primary ownership

| Query signal | Primary agent | Notes |
|---|---|---|
| post, article, email, landing, press release | copywriter | Needs verified facts for claims |
| SQL, metric, KPI, dashboard, retention, LTV, CAC | data_analyst | Needs data dictionary and formula |
| code, API, PR, GitHub, architecture, deploy | developer | Needs repo or spec context |
| FAQ, ticket, incident, error, user question | support | Escalates if confidence < 0.7 |
| market, competitor, roadmap, OKR, SWOT | strategist | Requires dated sources |
| invoice, act, tax, contract, reconciliation | accountant | Returns `needs_review` on missing source |

## Compound routing patterns

### Market research plus post

1. Strategist prepares facts, conclusions and limitations.
2. Copywriter turns verified input into the target channel format.
3. PMO checks that unsupported claims were not introduced.

### Product analytics plus executive memo

1. Data Analyst calculates metrics from approved sources.
2. Strategist interprets the business implications.
3. PMO summarizes decisions and risks.

### Bug report plus customer answer

1. Support classifies the issue and gathers repro steps.
2. Developer reviews technical cause if needed.
3. Support drafts a customer-safe answer.

### Invoice discrepancy

1. Accountant parses document data and checks arithmetic.
2. If legal details or tax rates are absent, status is `needs_review`.
3. PMO sends the result to the human finance owner.

