# Chart of accounts source requirements

> Parsed source metadata
>
> - Owner: `accountant`
> - Source id: `chart_of_accounts`
> - Source file: `data/raw_knowledge/accountant/chart_of_accounts/local__chart_of_accounts_requirements.md`
> - Source format: `md`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# Chart of accounts source requirements

## Rule

Accountant must use the company-approved chart of accounts. The local prototype
does not include a real chart yet.

## Required fields

| Field | Meaning |
|---|---|
| account_code | Account number/code |
| account_name | Approved account name |
| category | Asset, liability, equity, revenue, expense or other category |
| allowed_use | When the account may be used |
| restrictions | When it must not be used |
| effective_from | Start date |
| source | ERP/1C or finance document source |

## Missing-source behavior

If a transaction requires account classification and the chart is not loaded,
return `needs_review`.
