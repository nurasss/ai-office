# Report example: AI Office unit economics

## Summary

The business case estimates API cost per task for each AI Office agent. These
figures are planning assumptions and should be checked against real token usage
after the pilot starts.

## Planning table

| Agent | Estimated cost per task | Estimated cost per 1,000 tasks |
|---|---:|---:|
| PMO | $0.0135 | $13.50 |
| Data Analyst | $0.1180 | $118.00 |
| Developer | $0.1400 | $140.00 |
| Copywriter | $0.0390 | $39.00 |
| Support | $0.0735 | $73.50 |
| Strategist | $0.1200 | $120.00 |
| Accountant | $0.0855 | $85.50 |

## Interpretation

- PMO is the cheapest coordination layer and can handle high routing volume.
- Developer and Strategist tasks are costlier because they require stronger or
  longer-context reasoning.
- Accountant cost includes a two-step parse and audit approach.
- Support cost depends on the L1 to L2 escalation rate.

## Verification checklist

- Compare estimates with real token logs.
- Split input and output tokens by agent.
- Track route-only calls separately from full LLM calls.
- Track escalated and non-escalated support tickets separately.
- Do not mix API cost with infrastructure, storage, human review or integration
  licenses.

