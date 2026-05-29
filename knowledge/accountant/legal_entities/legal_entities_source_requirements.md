# Legal entities source requirements

## Rule

Legal entity details must come only from official finance/legal source files.
Do not infer BIN, IIN, bank account, address or signatory details.

## Required fields

| Field | Required |
|---|---|
| legal_entity_name | yes |
| BIN/IIN or registration id | yes |
| tax registration details | yes |
| bank name | yes |
| bank account | yes |
| SWIFT/BIC if applicable | conditional |
| legal address | yes |
| authorized signatory | conditional |
| source document date | yes |
| reviewed_by | yes |

## Missing-source behavior

Return `needs_review` if any required legal entity field is absent or stale.

