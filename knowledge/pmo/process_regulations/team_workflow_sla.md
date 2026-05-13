# PMO workflow and SLA

## Intake

PMO receives a task and classifies it by domain:

- text or announcement: Copywriter;
- code, API, GitHub or architecture: Developer;
- SQL, metrics, KPI or dashboards: Data Analyst;
- FAQ, incidents or user problems: Support;
- market, competitors, OKR or business plans: Strategist;
- invoices, acts, taxes or reconciliation: Accountant.

## Decomposition

For complex tasks PMO creates subtasks with:

- `task_id`;
- description;
- assigned agent;
- priority;
- dependencies;
- expected artifact;
- missing source list, if any.

## SLA defaults for pilot

These values are pilot defaults and must be replaced by official company SLA
documents when available.

| Work type | Agent | Target first draft | Escalation trigger |
|---|---|---:|---|
| Simple routing | PMO | 5 minutes | Ambiguous owner |
| Short post or email draft | Copywriter | 1 business day | Missing facts |
| SQL/report draft | Data Analyst | 1 business day | Missing schema or data |
| Code review note | Developer | 1 business day | Security or production risk |
| L1 support answer | Support | 2 hours | Confidence below 0.7 |
| Market memo | Strategist | 2 business days | No dated sources |
| Invoice check | Accountant | 4 hours | Missing legal/tax source |

## Status rules

- `todo`: task accepted, not started.
- `in_progress`: active agent is working.
- `blocked`: missing source, access or approval.
- `needs_review`: human review required before use.
- `done`: agent result delivered to PMO.

## Quality gate

PMO must send work back to the agent when:

- output ignores the requested format;
- required source is missing but not disclosed;
- numbers are not traceable;
- another agent's domain knowledge was used without verified handoff;
- final result lacks a next step or decision point.

