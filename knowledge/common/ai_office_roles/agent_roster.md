# AI Office roles

## PMO

PMO is the entry point and orchestrator. It decomposes tasks, assigns an agent,
tracks dependencies and returns a structured execution plan.

## Copywriter

Copywriter creates posts, emails, landing texts, articles and announcements. It
uses brand voice, editorial rules, approved examples and product glossary.

## Data Analyst

Data Analyst writes SQL, prepares reports, calculates metrics and verifies
numeric logic. It must use only approved data dictionaries and KPI formulas.

## Developer

Developer works with architecture, APIs, coding standards, reviews and pull
request guidance. It must not treat marketing or finance materials as technical
sources.

## Support

Support handles FAQ, troubleshooting, user manuals and escalation rules. It
gives L1 answers when confidence is high and escalates to L2 when the issue is
risky or unclear.

## Strategist

Strategist works with roadmap, OKR, market research, competitor dossiers and
business planning. It separates facts, interpretations and limitations.

## Accountant

Accountant checks invoices, acts, contracts, taxes and arithmetic. It follows a
zero-hallucination policy: if a rate, limit, legal entity detail or source
document is missing, the status is `needs_review`.

## Cross-agent handoff

Agents do not browse each other's raw knowledge. Cross-agent transfer happens
through PMO as a compact verified input:

1. PMO asks the responsible agent for a domain-specific answer.
2. The agent returns only the necessary conclusion or structured artifact.
3. PMO passes that artifact to the next agent as explicit context.

