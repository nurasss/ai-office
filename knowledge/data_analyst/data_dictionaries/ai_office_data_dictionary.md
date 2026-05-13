# AI Office data dictionary

## Source status

This file describes only the local AI Office prototype structures visible in the
repository. Production database schemas, dbt docs, Metabase descriptions and
warehouse tables are not connected yet.

## Office task API

### OfficeTaskRequest

| Field | Type | Meaning |
|---|---|---|
| task | string | User task for AI Office |
| agent_id | string | Agent to call directly, or `pmo` for routing |
| route_only | boolean | Return route and RAG hits without LLM call |
| notify_telegram | boolean | Send final answer to Telegram when env vars exist |

### OfficeTaskResponse

| Field | Type | Meaning |
|---|---|---|
| status | string | `ok`, `routed` or error state |
| task_id | string | Generated API task id |
| requested_agent | string | Agent requested by the client |
| handled_by | string | Agent selected for execution |
| handled_by_name | string | Human-readable agent name |
| result | string | Agent output |
| route | object | PMO route details |
| rag_hits | list | Compact list of RAG hits |
| telegram_notified | boolean | Whether Telegram notification was sent |

## RAG document shape

| Field | Type | Meaning |
|---|---|---|
| id | string | Stable document chunk id |
| content | string | Chunk text |
| metadata.agent_id | string | Owner agent or `common` |
| metadata.namespace | string | RAG namespace |
| metadata.source_id | string | Source id from catalog |
| metadata.source | string | Relative file path |
| metadata.chunk_index | integer | Chunk index inside source file |

## Missing production schemas

Before using Data Analyst for company metrics, load official schemas from:

- `pg_dump -s` for PostgreSQL DDL;
- dbt docs or manifest;
- Metabase/Tableau dashboard exports;
- CSV data dictionaries maintained by analytics.

