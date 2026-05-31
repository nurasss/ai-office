# Pilot Plan

## Week 1

Setup, Postgres/Redis/RQ worker, knowledge ingestion, GitHub/Telegram dry-run configuration.

## Week 2

PMO, Support and Developer scenarios with approvals and audit review.

## Week 3

Analyst scenarios, read-only SQL, evals and cost tracking review.

## Week 4

Stabilization, ROI report and go/no-go for expanded integrations.

## Controlled Pilot Commands

```bash
docker compose up -d postgres redis
alembic upgrade head
python run.py
python -m workers.rq_worker
python -m evals.runner
```

## KPIs

- task completion rate >= 70%
- first-pass acceptance >= 60%
- tool success rate >= 95%
- critical security incidents = 0
- RAG citation accuracy >= 80%
- approval coverage for dangerous actions = 100%
