# Pull request review guidelines

## Review priorities

1. Correctness and behavioral regressions.
2. Security and data isolation.
3. Error handling at API and tool boundaries.
4. Tests for changed behavior.
5. Readability and maintainability.

## AI Office-specific checks

- Agent knowledge must stay in the correct namespace.
- Finance, support, engineering and marketing data must not be mixed.
- Runtime memory under `data/` must not become source knowledge.
- Route-only flows must not spend LLM tokens.
- Missing credentials should produce a clear user-facing error.

## Comment style

Good review comments should:

- point to the exact risk;
- explain the user-visible impact;
- suggest a specific fix when possible;
- distinguish blockers from suggestions.

## PR description template

```markdown
## Summary

- 

## Verification

- [ ] Tests
- [ ] Manual route-only check
- [ ] RAG ingest dry-run if knowledge changed

## Risk

- 
```

