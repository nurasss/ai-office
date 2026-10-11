# Tools

All production-pilot tools use `tools.base.ToolAdapter`:

- `dry_run(args, context)`
- `execute(args, context)`
- `risk_level`
- `requires_approval`

P0 tools:

- `github.issue.create`: dry-run write, approval required.
- `github.issue.read`: safe fake read foundation.
- `telegram.notify`: external send, approval required when invoked as a tool.
- `sql_readonly.query`: SELECT/WITH/EXPLAIN only, one statement, row limit.
- `fake.draft` and `fake.delete`: deterministic test tools.

Approved GitHub writes execute only when all are true:

- `ENABLE_REAL_TOOLS=true`
- `GITHUB_TOKEN` is configured
- `GITHUB_OWNER` and `GITHUB_REPO` are configured

The GitHub client supports repository metadata, issue read/create/comment and pull request read/comment foundations. Delete, force push, secret mutation and merge operations are not implemented.

## Credential Behavior

Dry-run paths do not require provider credentials and must not call external
networks. Execute paths require exact credentials and return a readable
misconfiguration error when missing:

- GitHub: `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`
- Jira: `JIRA_URL`, `JIRA_USER`, `JIRA_API_TOKEN`
- Slack: `SLACK_BOT_TOKEN`
- Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

When `ENABLE_APPROVAL_REQUIRED=true`, write actions create a pending approval
and do not mutate external systems until approval. Execution success/failure is
recorded in audit events.
