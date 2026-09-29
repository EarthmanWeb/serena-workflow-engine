---
name: Ledger Domain Rules
description: Core validation rules for ledgerlite transactions — amount parsing and the fixed category set. Authoritative.
metadata:
  type: domain
---

# DOM_LEDGER_RULES — ledgerlite Domain Rules

Core business rules for ledgerlite's transaction model.

## Amount Parsing

- Amounts are decimal strings (e.g. `"12.34"`, `"-5"`, `"0.5"`) parsed to
  integer cents via `Decimal`. Anything that does not parse to a whole
  number of cents is invalid input (see `mem:ref/REF_ERROR_HANDLING`).
- Negative `amount_cents` = expense. Positive = income.

## Categories

- Fixed allowed set: `groceries`, `rent`, `utilities`, `transport`,
  `dining`, `salary`, `other`. Any other category (after alias resolution,
  see `mem:dom/DOM_INPUT_NORMALIZATION`) is invalid input.

Related: `mem:dom/DOM_INPUT_NORMALIZATION` (aliases accepted on input),
`mem:arch/ARCH_LEDGERLITE` (module layout), `mem:ref/REF_ERROR_HANDLING`
(error naming scheme).
