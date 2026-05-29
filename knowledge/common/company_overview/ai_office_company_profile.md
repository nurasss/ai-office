# AI Office: company profile

## Mission

AI Office helps a team move routine intellectual work into a controlled layer of
specialized AI employees. The goal is not to replace people, but to speed up
first drafts, checks, analysis and routing while keeping a human review step.

## Product

AI Office is a multi-agent digital office with seven virtual employees:

- PMO: routes and decomposes incoming work.
- Data Analyst: analyzes data, metrics and reports.
- Developer: writes and reviews code.
- Copywriter: prepares content and communication drafts.
- Support: answers L1/L2 support questions.
- Strategist: researches markets, competitors and strategy.
- Accountant: checks invoices, acts, taxes and financial arithmetic.

## Operating principle

- The user sends a task in natural language.
- PMO identifies the responsible agent or splits the task into subtasks.
- The selected agent uses only common corporate context and its own isolated
  knowledge namespace.
- The answer is returned as a draft or verified result for human review.

## Tone of voice

- Speak clearly and directly.
- Avoid exaggerated promises.
- Explain value through concrete actions and outcomes.
- If facts are missing, say so explicitly.
- Prefer practical next steps over abstract slogans.

## Knowledge isolation rule

Every agent can read:

- `common_corporate`;
- its own namespace, for example `agent_copywriter`.

Every agent must not read another agent's profile knowledge directly. If an
answer needs facts from another domain, PMO must request a verified input from
the relevant agent and pass only that extracted result onward.

