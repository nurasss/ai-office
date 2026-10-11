# Production Readiness

AI Office is packaged for a controlled production pilot, not open public SaaS.
Production mode is strict: no fake providers, SQLite, missing Redis, wildcard CORS,
missing API/admin/cron secrets, or Telegram bot without allowlists.

## Ready

- API key auth for public API routes.
- Dedicated `AI_OFFICE_ADMIN_TOKEN` for admin/dashboard and dangerous routes.
- Telegram webhook secret plus user/chat allowlists.
- Dry-run to approval to execute tool lifecycle for external write tools.
- Audit events for tasks, approvals, tool calls, scheduler jobs, and cron ticks.
- Alembic migrations for runtime tables, pgvector embeddings, and scheduler state.
- Docker Compose stack with API, migrate, RQ worker, scheduler, Postgres, Redis, and optional Telegram companion.
- Release archive and secret scan scripts.

## Production Preflight

```bash
python scripts/production_preflight.py
python scripts/production_preflight.py --env-file .env.production.example --template-check
```

When `ENVIRONMENT=production`, startup fails if required settings are unsafe.
Staging can use fake/dry-run providers for smoke checks, but production cannot.

## Required Commands

```bash
ruff check .
python scripts/check_no_secrets.py
alembic upgrade head
pytest -q
./scripts/make_release_archive.sh
python scripts/check_no_secrets.py dist/ai-office-release.zip
```

## Production Blockers Without Owner Inputs

- Real domain and HTTPS reverse proxy.
- Real Postgres password and backups.
- Real model provider key matching `MODEL_PROVIDER_PRIMARY`.
- Telegram bot token, webhook registration, and allowlisted user/chat IDs.
- GitHub/Jira/Slack credentials and scopes for real execution.
- Pilot budget caps and owner approval policy.
