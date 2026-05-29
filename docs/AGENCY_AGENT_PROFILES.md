# Agency Agent Profiles

## What This Is

AI Office can use curated professional profiles adapted from `agency-agents`.
Profiles specialize the existing AI Office employees with role context such as
Backend Architect, MCP Builder, Code Reviewer, Technical Writer, and Product
Strategist.

The profile layer is local and additive:

```text
adapted markdown profile
  -> AgentProfile
  -> AgentProfileRegistry
  -> PMO/task planning metadata
  -> existing AI Office runtime
```

## What This Is Not

This does not replace the AI Office runtime, task engine, approvals, scheduler,
Telegram security, API auth, or safe developer tools. Profiles are prompt and
routing context only. They do not grant permissions.

## Selected Profiles

| Profile ID | Name | Base Agent |
| --- | --- | --- |
| `developer.backend_architect` | Backend Architect | `developer` |
| `developer.code_reviewer` | Code Reviewer | `developer` |
| `developer.mcp_builder` | MCP Builder | `developer` |
| `developer.security_engineer` | Security Engineer | `developer` |
| `developer.devops_automator` | DevOps Automator | `developer` |
| `pmo.project_manager` | Project Manager | `pmo` |
| `copywriter.technical_writer` | Technical Writer | `copywriter` |
| `support.customer_support` | Customer Support Specialist | `support` |
| `analyst.data_engineer` | Data Engineer | `data_analyst` |
| `strategist.product_strategist` | Product Strategist | `strategist` |
| `accountant.document_reviewer` | Document Reviewer | `accountant` |

## How Routing Works

`AgentProfileRegistry.select_profile_for_task()` uses deterministic keyword
matching. It does not call an LLM.

Examples:

- `backend`, `api`, `integration`, `endpoint`, `database` -> `developer.backend_architect`
- `mcp`, `tool`, `server`, `context protocol` -> `developer.mcp_builder`
- `review`, `pr`, `pull request`, `code review` -> `developer.code_reviewer`
- `security`, `secret`, `auth`, `token`, `webhook`, `whitelist` -> `developer.security_engineer`
- `deploy`, `docker`, `ci`, `server`, `nginx`, `systemd` -> `developer.devops_automator`
- `docs`, `readme`, `manual`, `documentation` -> `copywriter.technical_writer`

If no profile matches, routing returns `None` and AI Office continues with the
base agent.

## Quality Gates

Profiles may declare a simple quality gate. For example:

```json
{
  "reviewer_profile": "developer.code_reviewer",
  "min_score": 85
}
```

For now, quality gates are configuration only. A later worker can use this to
run actual review tasks before results are marked final.

## Safety

Profiles do not override:

- API auth
- Telegram webhook secret validation
- Telegram user/chat allowlists
- CORS restrictions
- dangerous action detection
- approval requirements
- safe developer tools policy

Dangerous actions such as deploy, push to main, merge, delete files, change
secrets, send real email, write to CRM, charge payment, or unknown shell
commands still require approval.

## Why Not Import Everything

Importing every external role would create routing noise, prompt conflicts, and
tool-permission risk. AI Office keeps a small curated profile set that maps to
the seven existing employees and can be tested locally without network access.
