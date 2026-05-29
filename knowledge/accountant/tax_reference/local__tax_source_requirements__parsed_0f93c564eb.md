# Tax reference source requirements

> Parsed source metadata
>
> - Owner: `accountant`
> - Source id: `tax_reference`
> - Source file: `data/raw_knowledge/accountant/tax_reference/local__tax_source_requirements.md`
> - Source format: `md`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# Tax reference source requirements

## Rule

Tax rates are valid only when loaded from an official source with jurisdiction
and effective date. Accountant must not use generic or remembered rates.

## Required fields

| Field | Meaning |
|---|---|
| jurisdiction | Country or tax regime |
| tax_name | VAT, withholding tax, social tax or other tax |
| rate | Numeric rate |
| effective_from | Start date |
| effective_to | End date if known |
| source_document | Official source path or URL |
| reviewed_by | Finance owner |
| reviewed_at | Review date |

## Missing data behavior

If tax rate is not present for the jurisdiction and date, return:

```json
{
  "status": "needs_review",
  "notes": "Official tax rate source is not loaded for this jurisdiction/date."
}
```
