# Expense policy source requirements

> Parsed source metadata
>
> - Owner: `accountant`
> - Source id: `expense_policy`
> - Source file: `data/raw_knowledge/accountant/expense_policy/local__expense_policy_requirements.md`
> - Source format: `md`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# Expense policy source requirements

## Required policy sections

- Allowed expense categories.
- Forbidden expense categories.
- Daily allowance limits.
- Travel booking rules.
- Required receipts and documents.
- Currency conversion rule.
- Approval thresholds.
- Reimbursement timeline.

## Missing-source behavior

If the official expense policy is not loaded, Accountant must not approve or
reject an expense. Return `needs_review` and list the missing policy section.

## Output template

```json
{
  "status": "verified | discrepancy | needs_review",
  "expense_category": "",
  "policy_source": "",
  "limit": null,
  "amount": null,
  "difference": null,
  "notes": ""
}
```
