# AI Office business case summary

## Problem

Teams spend time on repeated intellectual tasks: reports, routing, content,
support answers, market analysis, code review and financial checks.

## Proposed solution

AI Office creates a layer of specialized AI employees. Each one handles a
defined task type with its own prompt, tools, model configuration and quality
rules.

## Business value

- Faster first drafts.
- More consistent task routing.
- Lower load on specialists for routine first-pass work.
- Better separation between content, code, analytics, support, strategy and
  finance contexts.
- Traceable source use through RAG metadata.

## Pilot economics

The initial business case estimates per-task API costs from about $0.0135 for
PMO routing to about $0.14 for developer tasks. These are planning assumptions
and must be validated against real token logs.

## Main risks

- Missing or outdated corporate source documents.
- Over-trusting drafts without human review.
- Mixing agent knowledge across domains.
- Financial or legal hallucinations if official sources are absent.
- Production vector backend not yet fully implemented.

