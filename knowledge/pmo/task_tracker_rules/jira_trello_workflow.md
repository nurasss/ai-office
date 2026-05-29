# Jira and Trello workflow rules

## Source status

This is a pilot workflow. Replace with exported Jira/Trello workflow settings
and labels when available.

## Status mapping

| PMO status | Jira/Trello status | Meaning |
|---|---|---|
| `todo` | To Do | Accepted but not started |
| `in_progress` | In Progress | Agent or human owner is working |
| `blocked` | Blocked | Missing source, access or decision |
| `needs_review` | Review | Human review required |
| `done` | Done | Result delivered and accepted |

## Labels

- `ai-office`
- `agent:pmo`
- `agent:copywriter`
- `agent:data-analyst`
- `agent:developer`
- `agent:support`
- `agent:strategist`
- `agent:accountant`
- `needs-source`
- `needs-human-review`

## PMO rule

PMO must include the selected agent, expected artifact and missing sources when
creating a task-tracker item.

