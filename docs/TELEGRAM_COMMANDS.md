# Telegram Commands

Telegram is the primary control interface for the autonomous MVP.

## Required Env

```text
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_WEBHOOK_SECRET=replace-with-long-random-value
ALLOWED_TELEGRAM_USER_IDS=123456789
ALLOWED_TELEGRAM_CHAT_IDS=123456789
```

Set webhook:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -d "url=https://your-domain/api/telegram/webhook" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

## Commands

```text
/tasks
/tasks open
/tasks today
/plan
/projects
/project ai-office
/approve <approval_id>
/reject <approval_id>
/autonomy status
/autonomy on
/autonomy off
```

Existing agent commands still work:

```text
/pmo задача
/agent developer задача
/all задача
/bind developer
/agents
```

Agents can use public read-only web context when a Telegram task clearly asks
for current information, for example:

```text
/agent strategist актуальные новости рынка платежей в Казахстане
/agent developer latest FastAPI docs по lifespan
```

This is search/read-only access. Approvals and dangerous-action policy still
apply to deploys, pushes, writes, CRM/email/payment actions, and shell commands.

## Behavior

- `/tasks`: shows open tasks grouped by project with status, agent, and priority.
- `/plan`: runs the daily planning loop immediately and saves created tasks.
- `/project <slug>`: shows goal, active tasks, recent events, and next-step hint.
- `/approve <id>`: marks a pending approval as approved and queues the task if it was waiting.
- `/reject <id>`: marks approval rejected and cancels the waiting task.
- `/autonomy on|off`: toggles the in-process runtime flag without editing env.

Approval requests also include inline buttons:

```text
✅ Approve
❌ Reject
```

Callback data uses `approval:approve:<id>` and `approval:reject:<id>`. The callback user and chat must pass the same whitelist checks as normal messages. Expired or already resolved approvals cannot be approved again.

`/autonomy status` shows scheduler state, task counts, pending/expired approvals, last daily/evening run timestamps, and DB connectivity.
