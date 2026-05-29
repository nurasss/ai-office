# Деплой AI Office

Проект является FastAPI-приложением. Для Vercel используется zero-config entrypoint `app.py`, который импортирует `web.app:app`.

Для личного 24/7 режима предпочтительнее VPS/Docker Compose с PostgreSQL. Vercel подходит для демо/API, но in-process scheduler может засыпать вместе с serverless runtime.

## Вариант: GitHub -> Vercel

1. Создать GitHub-репозиторий и запушить проект.
2. Открыть Vercel Dashboard.
3. Выбрать Add New -> Project.
4. Импортировать GitHub-репозиторий.
5. Framework Preset оставить `Other`.
6. Build Command оставить пустым.
7. Output Directory оставить пустым.
8. В Environment Variables добавить:

```text
OPENAI_API_KEY=<secret>
AI_OFFICE_REQUIRE_API_KEY=true
AI_OFFICE_API_KEY=<long-random-secret>
TELEGRAM_WEBHOOK_SECRET=<long-random-secret>
ALLOWED_TELEGRAM_USER_IDS=<your-user-id>
ALLOWED_TELEGRAM_CHAT_IDS=<your-chat-id>
```

Опционально можно поменять модели:

```text
OPENAI_DEFAULT_MODEL=gpt-5.5
OPENAI_HEAVY_MODEL=gpt-5.5
TELEGRAM_BOT_TOKEN=<secret>
TELEGRAM_PMO_BOT_TOKEN=<secret>
TELEGRAM_DATA_ANALYST_BOT_TOKEN=<secret>
TELEGRAM_DEVELOPER_BOT_TOKEN=<secret>
TELEGRAM_COPYWRITER_BOT_TOKEN=<secret>
TELEGRAM_SUPPORT_BOT_TOKEN=<secret>
TELEGRAM_STRATEGIST_BOT_TOKEN=<secret>
TELEGRAM_ACCOUNTANT_BOT_TOKEN=<secret>
TELEGRAM_CHAT_ID=<chat-id>
TELEGRAM_GENERAL_THREAD_ID=
TELEGRAM_PMO_THREAD_ID=
TELEGRAM_DATA_ANALYST_THREAD_ID=
TELEGRAM_DEVELOPER_THREAD_ID=
TELEGRAM_COPYWRITER_THREAD_ID=
TELEGRAM_SUPPORT_THREAD_ID=
TELEGRAM_STRATEGIST_THREAD_ID=
TELEGRAM_ACCOUNTANT_THREAD_ID=
```

7. Запустить деплой.
8. После запуска проверить:

```text
https://<your-render-domain>/health
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

## Локальная подготовка GitHub-репозитория

```bash
git init
git branch -M main
git add .
git commit -m "Prepare AI Office for Vercel deployment"
gh repo create ai-office --private --source=. --remote=origin --push
```

Если нужен публичный репозиторий, заменить `--private` на `--public`.

## Альтернатива: любой Docker-хостинг

Проект также содержит `Dockerfile`, поэтому его можно развернуть на Render, Railway, Fly.io, VPS, Google Cloud Run или другом Docker-хостинге.

Минимальные переменные окружения:

```text
OPENAI_API_KEY=<secret>
OPENAI_DEFAULT_MODEL=gpt-5.5
OPENAI_HEAVY_MODEL=gpt-5.5
AI_OFFICE_REQUIRE_API_KEY=true
AI_OFFICE_API_KEY=<long-random-secret>
DATABASE_URL=postgresql+psycopg2://ai_office:<password>@postgres:5432/ai_office
TELEGRAM_BOT_TOKEN=<secret>
TELEGRAM_CHAT_ID=<chat-id>
TELEGRAM_WEBHOOK_SECRET=<long-random-secret>
ALLOWED_TELEGRAM_USER_IDS=<your-user-id>
ALLOWED_TELEGRAM_CHAT_IDS=<your-chat-id>
AI_OFFICE_TASK_STUCK_TIMEOUT_MINUTES=30
AI_OFFICE_TASK_MAX_RETRIES=2
AI_OFFICE_APPROVAL_TTL_HOURS=24
AUTONOMY_ENABLED=true
CRON_SECRET=<long-random-secret>
ENVIRONMENT=production
LOG_LEVEL=INFO
```

`TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` нужны для уведомления после завершения PMO-задачи. Если они не заданы, чат продолжит работать, но уведомление будет пропущено.

## 24/7 autonomy tick on Vercel Hobby

Vercel Hobby не поддерживает частые Vercel Cron Jobs. Поэтому в репозитории есть
GitHub Actions workflow `.github/workflows/autonomy-cron.yml`, который дергает
защищенный endpoint каждые 15 минут:

```text
https://ai-office-one.vercel.app/api/cron/autonomy-tick
```

Для него нужны GitHub repository secrets:

```text
AI_OFFICE_CRON_URL=https://ai-office-one.vercel.app/api/cron/autonomy-tick
AI_OFFICE_CRON_SECRET=<same value as Vercel CRON_SECRET>
```

## Telegram chat / channel webhook

Чтобы Telegram стал рабочим чатом для агентов, добавьте нужных ботов в группу
или канал и назначьте webhook на production-домен.

Один общий PMO bot:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -d "url=https://ai-office-one.vercel.app/api/telegram/webhook" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

Отдельный bot на каждого агента:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_PMO_BOT_TOKEN>/setWebhook" \
  -d "url=https://ai-office-one.vercel.app/api/telegram/webhook/pmo" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"

curl "https://api.telegram.org/bot<TELEGRAM_DATA_ANALYST_BOT_TOKEN>/setWebhook" \
  -d "url=https://ai-office-one.vercel.app/api/telegram/webhook/data_analyst" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"

curl "https://api.telegram.org/bot<TELEGRAM_DEVELOPER_BOT_TOKEN>/setWebhook" \
  -d "url=https://ai-office-one.vercel.app/api/telegram/webhook/developer" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"

curl "https://api.telegram.org/bot<TELEGRAM_COPYWRITER_BOT_TOKEN>/setWebhook" \
  -d "url=https://ai-office-one.vercel.app/api/telegram/webhook/copywriter" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"

curl "https://api.telegram.org/bot<TELEGRAM_SUPPORT_BOT_TOKEN>/setWebhook" \
  -d "url=https://ai-office-one.vercel.app/api/telegram/webhook/support" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"

curl "https://api.telegram.org/bot<TELEGRAM_STRATEGIST_BOT_TOKEN>/setWebhook" \
  -d "url=https://ai-office-one.vercel.app/api/telegram/webhook/strategist" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"

curl "https://api.telegram.org/bot<TELEGRAM_ACCOUNTANT_BOT_TOKEN>/setWebhook" \
  -d "url=https://ai-office-one.vercel.app/api/telegram/webhook/accountant" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

Поддерживаемые команды:

```text
/tasks
/tasks today
/plan
/projects
/project ai-office
/approve <id>
/reject <id>
/autonomy status
/autonomy on
/autonomy off
/pmo задача
/agent developer задача
/agent data_analyst задача
/all задача
/agents
```

Без команды сообщение обрабатывается через PMO.

### Telegram Topics

Для группы с темами можно сделать `General` входящей темой: сообщение без команды
попадает к PMO, PMO выбирает исполнителя, затем задача и результат публикуются в
тему нужного агента.

Надежный production-вариант: сохранить `message_thread_id` тем в Vercel env
через переменные `TELEGRAM_*_THREAD_ID`. Быстрый способ узнать и привязать тему:
отправьте команду внутри каждой Telegram Topic:

```text
/bind general
/bind pmo
/bind data_analyst
/bind developer
/bind copywriter
/bind support
/bind strategist
/bind accountant
```

Для чтения обычных сообщений в группе у PMO-бота должна быть отключена Privacy
Mode в BotFather или сообщения должны приходить как команды/упоминания.

Перед первым запуском persistent database примените миграции:

```bash
alembic upgrade head
```

Для будущих изменений схемы:

```bash
alembic revision --autogenerate -m "describe_change"
alembic upgrade head
```

`init_db()` остается только быстрым локальным fallback-ом; на VPS/PostgreSQL предпочтительны Alembic migrations.

Команда запуска внутри контейнера уже задана:

```bash
python run.py
```

Приложение слушает порт из переменной `PORT`, которую обычно автоматически задает хостинг. Если `PORT` не задан, используется `8000`.

## Важно по безопасности

Не загружайте файл `.env` на GitHub или хостинг как файл. Ключи нужно добавлять только через Environment Variables в панели хостинга.

Текущий `.gitignore` исключает `.env`, `.vercel/`, `.venv/`, `data/`, `reports/`, runtime SQLite-файлы и приватные ключи.

## VPS Docker Compose пример

```yaml
services:
  app:
    build: .
    command: python run.py
    ports:
      - "8000:8000"
    environment:
      ENVIRONMENT: production
      AI_OFFICE_REQUIRE_API_KEY: "true"
      AI_OFFICE_API_KEY: ${AI_OFFICE_API_KEY}
      DATABASE_URL: postgresql+psycopg2://ai_office:${POSTGRES_PASSWORD}@postgres:5432/ai_office
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      TELEGRAM_CHAT_ID: ${TELEGRAM_CHAT_ID}
      TELEGRAM_WEBHOOK_SECRET: ${TELEGRAM_WEBHOOK_SECRET}
      ALLOWED_TELEGRAM_USER_IDS: ${ALLOWED_TELEGRAM_USER_IDS}
      ALLOWED_TELEGRAM_CHAT_IDS: ${ALLOWED_TELEGRAM_CHAT_IDS}
      AUTONOMY_ENABLED: "true"
      AUTONOMY_TIMEZONE: Asia/Almaty
      AI_OFFICE_TASK_STUCK_TIMEOUT_MINUTES: "30"
      AI_OFFICE_TASK_MAX_RETRIES: "2"
      AI_OFFICE_APPROVAL_TTL_HOURS: "24"
    depends_on:
      - postgres

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: ai_office
      POSTGRES_USER: ai_office
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```
