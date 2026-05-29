# Finance document templates

> Parsed source metadata
>
> - Owner: `accountant`
> - Source id: `invoice_templates`
> - Source file: `data/raw_knowledge/accountant/document_templates/local__invoice_act_contract_templates.md`
> - Source format: `md`
> - Parser: `scripts/parse_knowledge_sources.py`

---

# Finance document templates

## Source status

These are structural templates for parsing and validation. They are not official
legal templates. Replace with approved CFO/legal documents before production.

## Invoice fields

| Field | Required | Notes |
|---|---|---|
| invoice_number | yes | Must match source document |
| invoice_date | yes | Use original date |
| seller_legal_entity | yes | Must match legal entity card |
| buyer_legal_entity | yes | Must match contract or invoice |
| currency | yes | Use document currency |
| line_items | yes | Description, quantity, unit price, tax |
| subtotal | yes | Sum before tax |
| tax_amount | conditional | Required when tax applies |
| total | yes | Final payable amount |
| payment_terms | conditional | Required when present in contract |

## Act fields

- act number;
- act date;
- contract reference;
- service period;
- service description;
- amount;
- tax amount if applicable;
- signatures or approval references.

## Contract fields

- contract number;
- parties;
- subject;
- payment terms;
- currency;
- tax treatment;
- effective date;
- termination terms;
- responsible owner.
