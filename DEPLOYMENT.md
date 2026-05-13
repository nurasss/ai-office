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
TELEGRAM_PMO_BOT_TOKEN=123456789:...
TELEGRAM_DATA_ANALYST_BOT_TOKEN=123456789:...
TELEGRAM_DEVELOPER_BOT_TOKEN=123456789:...
TELEGRAM_COPYWRITER_BOT_TOKEN=123456789:...
TELEGRAM_SUPPORT_BOT_TOKEN=123456789:...
TELEGRAM_STRATEGIST_BOT_TOKEN=123456789:...
TELEGRAM_ACCOUNTANT_BOT_TOKEN=123456789:...
TELEGRAM_CHAT_ID=123456789
TELEGRAM_WEBHOOK_SECRET=long-random-string
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

Команда запуска внутри контейнера уже задана:

```bash
python run.py
```

Приложение слушает порт из переменной `PORT`, которую обычно автоматически задает хостинг. Если `PORT` не задан, используется `8000`.

## Важно по безопасности

Не загружайте файл `.env` на GitHub или хостинг как файл. Ключи нужно добавлять только через Environment Variables в панели хостинга.

Текущий `.gitignore` уже исключает `.env`.
