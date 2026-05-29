# Finance approval matrix

> Parsed source metadata
>
> - Owner: `accountant`
> - Source id: `approval_matrix`
> - Source file: `data/raw_knowledge/accountant/approval_matrix/local__finance_approval_matrix.md`
> - Source format: `md`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# Finance approval matrix

## Source status

This is a pilot placeholder. Replace with the official CFO approval matrix.

## Default pilot routing

| Case | Status | Required reviewer |
|---|---|---|
| Missing legal entity details | `needs_review` | Finance owner |
| Missing tax rate | `needs_review` | Finance owner |
| Missing contract reference | `needs_review` | Legal or finance owner |
| Arithmetic discrepancy | `discrepancy` | Finance owner |
| Expense category not loaded | `needs_review` | Finance owner |

## Approval rule

No invoice, act, tax decision or expense reimbursement should be marked
production-approved by the agent. The agent can only prepare a structured check
and recommend the next reviewer.
