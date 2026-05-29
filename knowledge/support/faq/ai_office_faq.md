# AI Office FAQ

## What is AI Office?

AI Office is a controlled digital office with seven specialized AI employees:
PMO, Data Analyst, Developer, Copywriter, Support, Strategist and Accountant.

## Why not use one universal chat?

Each agent has its own role, tools, prompt and knowledge namespace. This reduces
the chance that marketing style, code rules, support scripts and finance rules
are mixed in one answer.

## What does PMO do?

PMO receives the task, chooses the responsible agent, splits complex work into
subtasks and returns route metadata.

## What is route-only mode?

Route-only mode shows which agent would handle the task and which RAG documents
matched, without calling an LLM.

## Why does an agent say it needs a source?

Some tasks require official company data. Data Analyst needs schemas or files,
Accountant needs legal and tax sources, and Strategist needs dated market
sources. The correct behavior is to ask for the source instead of guessing.

## Can AI Office publish or approve final work?

In the current pilot, no. Outputs are drafts, checks or recommendations for
human review unless a separate approval process is configured.

