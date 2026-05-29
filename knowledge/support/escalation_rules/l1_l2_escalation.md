# Support L1/L2 escalation rules

## Escalate to L2 when

- Confidence is below 0.7.
- The issue requires code, infrastructure or database access.
- The user reports a critical workflow is blocked.
- The same L1 answer failed twice.
- The answer could expose private, financial or security-sensitive data.

## Escalate to a human when

- Legal, finance or contract interpretation is required.
- The user asks for personal data deletion or access rights.
- The issue may affect many users.
- Production deployment or rollback is required.
- No approved troubleshooting guide exists.

## L1 answer format

```markdown
## Diagnosis

## Steps

## Confidence

## Escalation
```

## Ticket note format

```markdown
Source: user/manual/system
Symptoms:
Steps attempted:
Result:
Confidence:
Escalation reason:
```

