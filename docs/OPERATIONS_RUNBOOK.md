# AI Office Operations Runbook

## Local Start

```bash
cp .env.example .env
docker compose up -d postgres redis
alembic upgrade head
python run.py
```

Open `http://localhost:8000/health` and `http://localhost:8000/ready`.

## Worker

Run the deterministic local worker:

```bash
python -m workers.runner
```

It processes tasks with status `pending` or `queued`.

Run the Redis/RQ worker:

```bash
python -m workers.rq_worker
```

If Redis is unavailable, `/api/tasks` falls back to the DB-backed queue marker and records `task.enqueued`.

## Tests

```bash
pytest -q
```

Tests use fake providers/tools and do not require API keys.

## Audit

- All audit events: `GET /api/audit`
- Task audit: `GET /api/tasks/{task_id}/audit`

If `AI_OFFICE_REQUIRE_API_KEY=true`, pass `X-API-Key`.

## Approvals

- List: `GET /api/approvals`
- Detail: `GET /api/approvals/{id}`
- Approve: `POST /api/approvals/{id}/approve`
- Reject: `POST /api/approvals/{id}/reject`

Use `X-User-Role: manager` or stronger for approval decisions.

## GitHub

Set:

```env
GITHUB_TOKEN=
GITHUB_OWNER=
GITHUB_REPO=
ENABLE_REAL_TOOLS=false
```

P0 supports safe dry-run issue creation and approval creation. Real writes remain disabled unless `ENABLE_REAL_TOOLS=true`.
P1 executes approved GitHub issue creation through the REST API when `ENABLE_REAL_TOOLS=true` and token/owner/repo are configured.

## Telegram

Set:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ALLOWED_TELEGRAM_USER_IDS=
ALLOWED_TELEGRAM_CHAT_IDS=
```

If the token or chat ID is missing, notifications are skipped and tasks continue.

## Postgres/Redis

```bash
docker compose up -d postgres redis
docker compose ps
```

`/ready` checks DB connectivity and Redis TCP reachability.

## Knowledge Upload

```bash
curl -X POST -H "Content-Type: application/json" \
  http://localhost:8000/api/knowledge/upload \
  -d '{"agent_namespace":"agent_support","title":"GitHub setup","content":"GitHub integration setup uses token placeholders."}'
curl "http://localhost:8000/api/knowledge/search?query=GitHub&agent_namespace=agent_support"
```

## Evals

```bash
python -m evals.runner
```

## Smoke Test

With the app running:

```bash
bash scripts/pilot_smoke_test.sh
```
