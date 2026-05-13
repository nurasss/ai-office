# Деплой AI Office на GitHub + Vercel

Проект является FastAPI-приложением. Для Vercel используется zero-config entrypoint `app.py`, который импортирует `web.app:app`.

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
OPENAI_API_KEY=sk-...
```

Опционально можно поменять модели:

```text
OPENAI_DEFAULT_MODEL=gpt-4o-mini
OPENAI_HEAVY_MODEL=gpt-4o
TELEGRAM_BOT_TOKEN=123456789:...
TELEGRAM_CHAT_ID=123456789
TELEGRAM_WEBHOOK_SECRET=long-random-string
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
OPENAI_API_KEY=sk-...
OPENAI_DEFAULT_MODEL=gpt-4o-mini
OPENAI_HEAVY_MODEL=gpt-4o
TELEGRAM_BOT_TOKEN=123456789:...
TELEGRAM_CHAT_ID=123456789
ENVIRONMENT=production
LOG_LEVEL=INFO
```

`TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` нужны для уведомления после завершения PMO-задачи. Если они не заданы, чат продолжит работать, но уведомление будет пропущено.

## Telegram chat / channel webhook

Чтобы Telegram стал рабочим чатом для агентов, добавьте бота в группу или канал
и назначьте webhook на production-домен:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -d "url=https://ai-office-one.vercel.app/api/telegram/webhook" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

Поддерживаемые команды:

```text
/pmo задача
/agent developer задача
/agent data_analyst задача
/all задача
/agents
```

Без команды сообщение обрабатывается через PMO.

Команда запуска внутри контейнера уже задана:

```bash
python run.py
```

Приложение слушает порт из переменной `PORT`, которую обычно автоматически задает хостинг. Если `PORT` не задан, используется `8000`.

## Важно по безопасности

Не загружайте файл `.env` на GitHub или хостинг как файл. Ключи нужно добавлять только через Environment Variables в панели хостинга.

Текущий `.gitignore` уже исключает `.env`.
