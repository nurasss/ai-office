# Basic troubleshooting tree

## Step 1: Identify the problem class

- Login or access.
- API request failure.
- Telegram notification.
- RAG or missing knowledge.
- LLM credentials.
- Unexpected agent routing.

## Step 2: Gather minimum details

- What did the user try?
- What exact error appeared?
- Which agent was selected?
- Was route-only mode enabled?
- Did the issue happen once or repeatedly?

## Step 3: Known checks

### Missing LLM credentials

If the API returns a missing credentials error, ask the owner to configure the
required environment variables. Do not ask the user to paste secrets into chat.

### Wrong route

Ask for the task text and run route-only mode. If PMO selected the wrong agent,
add the missing keyword or rule to PMO routing knowledge and code if needed.

### No RAG hits

Check that the source file is in `knowledge/<agent>/...` and run ingest again.

## Step 4: Escalate

Escalate when the issue requires source code, infrastructure logs, finance/legal
approval, or production credentials.

