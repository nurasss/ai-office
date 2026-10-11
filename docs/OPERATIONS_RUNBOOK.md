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
./scripts/staging_smoke.sh
python scripts/check_migrations.py
python scripts/telegram_webhook_smoke.py
```

## Production Preflight

```bash
python scripts/production_preflight.py
python scripts/production_preflight.py --env-file .env.production.example --template-check
```

`ENVIRONMENT=production` fails fast for missing API/admin/cron secrets, SQLite,
missing Redis, fake model or embedding providers, wildcard CORS, missing
Telegram allowlists, and unsafe tool/autonomy combinations.

## Admin Access

Admin/dashboard pages and dangerous endpoints require:

```text
Authorization: Bearer <AI_OFFICE_ADMIN_TOKEN>
```

Use the public API key only for normal API clients:

```text
X-API-Key: <AI_OFFICE_API_KEY>
```

## Backup and Restore

Backup:

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U ai_office -d ai_office -Fc -f /tmp/ai_office.dump
docker compose -f docker-compose.prod.yml cp postgres:/tmp/ai_office.dump ./ai_office.dump
```

Restore to a new database:

```bash
docker compose -f docker-compose.prod.yml cp ./ai_office.dump postgres:/tmp/ai_office.dump
docker compose -f docker-compose.prod.yml exec postgres \
  pg_restore -U ai_office -d ai_office --clean --if-exists /tmp/ai_office.dump
```

## Secret Rotation

1. Generate a replacement secret.
2. Update `.env.production` or the deployment secret store.
3. Restart only affected services.
4. Re-run `python scripts/production_preflight.py`.
5. Revoke the old provider token.

Rotate `AI_OFFICE_API_KEY`, `AI_OFFICE_ADMIN_TOKEN`, `CRON_SECRET`, Telegram,
GitHub, Jira, Slack, and model provider keys independently.

## Pilot KPIs

Track task completion rate, stuck/failed tasks, approval latency, cost per task,
Telegram response time, RAG citation coverage, and user satisfaction for the
four-week pilot.
