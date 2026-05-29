# Security

This project is designed for personal use, but private APIs and Telegram control paths are still locked down.

## Secrets

Never commit:

```text
.env
.venv/
.vercel/
.pytest_cache/
__pycache__/
data/
reports/
workspaces/
*.pem
*.key
```

`.gitignore`, `.dockerignore`, and `.vercelignore` exclude these paths. If a real token was ever committed, rotate it at the provider.

## API Auth

For the personal Telegram-first runtime, API key auth is off by default:

```text
AI_OFFICE_REQUIRE_API_KEY=false
```

This removes the `X-API-Key` requirement for local/personal API checks. Telegram
is still protected by webhook secret and allowlists.

For a public server, enable API key auth:

```text
AI_OFFICE_REQUIRE_API_KEY=true
AI_OFFICE_API_KEY=replace-with-long-random-value
```

When enabled, private/autonomous endpoints accept:

```text
X-API-Key: <value>
Authorization: Bearer <value>
```

Telegram webhook is public only at the network level; it requires the Telegram
secret header and whitelist. Keep `AI_OFFICE_REQUIRE_API_KEY=true` on any
public deployment where `/api/*` is reachable by other people.

## Telegram Security

Required:

```text
TELEGRAM_WEBHOOK_SECRET=replace-with-long-random-value
ALLOWED_TELEGRAM_USER_IDS=123456789
ALLOWED_TELEGRAM_CHAT_IDS=123456789
```

Webhook requests must include:

```text
X-Telegram-Bot-Api-Secret-Token: <TELEGRAM_WEBHOOK_SECRET>
```

Messages from non-whitelisted users or chats are rejected before any agent/task work starts.

Inline approval callbacks use the same whitelist checks. Pending approvals can expire through `AI_OFFICE_APPROVAL_TTL_HOURS`; expired or already resolved approvals cannot be approved later.

## CORS

Set explicit origins:

```text
AI_OFFICE_ALLOWED_ORIGINS=http://localhost:8000,http://localhost:5173,https://your-domain.kz
```

The app no longer uses `allow_origins=["*"]`.

## Action Policy

Automatically allowed:

- project/task analysis;
- creating and updating tasks;
- plans, reports, draft results;
- allowed file reads/searches inside `AI_OFFICE_WORKSPACE_ROOT`;
- read-only public web search/fetch when `AI_OFFICE_WEB_ACCESS_ENABLED=true`;
- safe allowlisted test/build commands.

Requires approval:

- deploy/production changes;
- push/merge to remote/main;
- deleting files;
- sending emails or mass messages;
- CRM/Bitrix writes;
- secrets/env changes;
- money-spending actions;
- shell commands outside `AI_OFFICE_SAFE_COMMANDS`.

Task lifecycle hardening:

- `AI_OFFICE_TASK_STUCK_TIMEOUT_MINUTES` controls when running tasks are considered stuck.
- `AI_OFFICE_TASK_MAX_RETRIES` prevents infinite retry loops for failed/stuck tasks.
- Every retry, stuck transition, approval decision, and approval expiration writes a task event.

Forbidden by the tools layer:

- path traversal outside workspace;
- public web fetches to localhost/private IPs, non-http(s) schemes, or URLs with credentials;
- shell metacharacters in commands;
- obviously destructive command families such as `rm`, `sudo`, `ssh`, `docker`, `kubectl`, `vercel`.

## Public Web Access

Agents can use read-only public web context for tasks that look time-sensitive,
for example "latest docs", "актуальные новости", prices, releases, laws, market
or competitor checks.

```text
AI_OFFICE_WEB_ACCESS_ENABLED=true
AI_OFFICE_WEB_SEARCH_MAX_RESULTS=5
AI_OFFICE_WEB_FETCH_MAX_CHARS=6000
```

The web layer only reads public HTTP(S) pages. It blocks localhost, private IP
ranges, `file://`, URLs with credentials, and non-text content. It does not log
in, submit forms, buy anything, send messages, or bypass approvals.
