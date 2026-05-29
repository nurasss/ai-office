# Deployment Workflow

Template deployment memory. Do not store credentials here.

- Prefer VPS + Docker Compose + PostgreSQL for 24/7 autonomy.
- Keep deploy, rollback, domain changes, and env changes behind approvals.
- Verify `/health` and Telegram webhook after deployment.

