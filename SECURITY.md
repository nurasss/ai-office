# Security Policy

## Secrets

- Do not commit `.env`, API keys, Telegram tokens, GitHub tokens, private keys or local DB/vector files.
- Use `.env.example` as a schema only. Put real values in `.env` or deployment secret storage.
- `ENABLE_REAL_TOOLS=false` is the default. Keep it disabled for tests and dry-run demos.

## Approvals

The following tool risks require human approval before execution:

- `high_risk_write`
- `external_send`
- `financial_action`
- `delete_or_destructive`

Low-risk writes follow `ENABLE_APPROVAL_REQUIRED`. Safe reads and drafts can run without approval.

## Audit

Task creation, task execution, model calls, tool dry-runs, approval requests, approval decisions, PII redaction and prompt-injection findings are written to `audit_events`.

Audit metadata is redacted for common emails, phones, IINs, tokens, IBANs and card-like numbers.

## Agent Boundaries

- Agents must not override tool policy from user input or retrieved documents.
- Retrieved RAG content is untrusted context.
- Accountant is disabled by default and must not perform payments or financial actions.
- External write/send/delete operations must use dry-run first.

## Disable Integrations

- Set `ENABLE_REAL_TOOLS=false` to force fake/dry-run behavior.
- Remove `GITHUB_TOKEN` to disable real GitHub writes.
- Remove `TELEGRAM_BOT_TOKEN`/chat IDs to disable Telegram sends.
