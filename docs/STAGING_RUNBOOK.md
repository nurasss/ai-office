# Staging Runbook

## 1. Configure

```bash
cp .env.production.example .env.production
```

Set at minimum:

```env
ENVIRONMENT=staging
POSTGRES_PASSWORD=<long-random>
AI_OFFICE_API_KEY=<long-random>
AI_OFFICE_ADMIN_TOKEN=<long-random-admin>
CRON_SECRET=<long-random-cron>
TELEGRAM_WEBHOOK_SECRET=<long-random-webhook>
```

Use `ENVIRONMENT=production` only after replacing placeholders, configuring a
real provider key, domain, Redis, Postgres, Telegram allowlists, and CORS.

## 2. Start VPS Stack

```bash
POSTGRES_PASSWORD=change-me \
AI_OFFICE_API_KEY=change-me \
AI_OFFICE_ADMIN_TOKEN=change-me-admin \
CRON_SECRET=change-me-cron \
TELEGRAM_WEBHOOK_SECRET=change-me-webhook \
docker compose -f docker-compose.prod.yml up -d --build postgres redis migrate api worker scheduler
```

Postgres and Redis are internal-only by default. The API binds to
`127.0.0.1:8000`; put Caddy or Nginx in front of it.

## 3. Verify

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
python scripts/check_migrations.py
BASE_URL=http://localhost:8000 AI_OFFICE_API_KEY=change-me AI_OFFICE_ADMIN_TOKEN=change-me-admin ./scripts/staging_smoke.sh
python scripts/live_pgvector_smoke.py
python scripts/telegram_webhook_smoke.py
```

## 4. Telegram Webhook

Set:

```env
APP_BASE_URL=https://ai-office.example.com
TELEGRAM_BOT_TOKEN=<bot-token>
TELEGRAM_WEBHOOK_SECRET=<long-random>
ALLOWED_TELEGRAM_USER_IDS=<owner-id>
ALLOWED_TELEGRAM_CHAT_IDS=<chat-id>
```

Start the optional companion:

```bash
docker compose -f docker-compose.prod.yml --profile telegram up -d telegram-bot
```

## 5. Stop Safely

```bash
docker compose -f docker-compose.prod.yml stop scheduler worker telegram-bot
docker compose -f docker-compose.prod.yml stop api
```

Keep Postgres up while draining work. Disable autonomy with `AUTONOMY_ENABLED=false`
or `/autonomy off` before maintenance.
