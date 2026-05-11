# Accountant zero-hallucination policy

> Parsed source metadata
>
> - Owner: `accountant`
> - Source id: `accounting_policy`
> - Source file: `data/raw_knowledge/accountant/accounting_policy/local__zero_hallucination_policy.md`
> - Source format: `md`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# Accountant zero-hallucination policy

## Core rule

Accountant must not infer financial, legal, tax or bank details from general
knowledge. If the official source is not loaded, the output status is
`needs_review`.

## Required source types

- Expense policy.
- Legal entity cards with BIN/IIN and bank accounts.
- Tax rate reference with jurisdiction and effective date.
- Contract, invoice and act templates.
- Chart of accounts.
- Approval matrix.

## Allowed statuses

| Status | Meaning |
|---|---|
| `verified` | Source data exists and arithmetic checks passed |
| `discrepancy` | Source data exists and mismatch was found |
| `needs_review` | Source data is incomplete, absent or ambiguous |

## Mandatory checks

- Sum of line items equals subtotal.
- Tax calculation matches the loaded rate and base.
- Grand total equals subtotal plus taxes and adjustments.
- Document number, date, counterparty and legal entity match.
- Expense category is allowed by policy.
- Approval route matches the amount and category.

## Missing official data

Current repository does not contain real company tax rates, legal entity
requisites or chart of accounts. Any request depending on those details must be
returned as `needs_review` until official finance documents are loaded.
