---
name: Ledger Domain Rules
description: Validation rules, error codes, category aliases, and core transaction rules for ledgerlite. Authoritative — hidden acceptance tests grade against these rules exactly.
metadata:
  type: domain
---

# DOM_LEDGER_RULES — ledgerlite Domain Rules

Authoritative business rules for ledgerlite. These rules are NOT restated in
task prompts — implement exactly what is specified here.

## Amount Parsing

- Amounts are decimal strings (e.g. `"12.34"`, `"-5"`, `"0.5"`) parsed to
  integer cents via `Decimal`. Anything that does not parse to a whole
  number of cents raises `LedgerError(E_INVALID_AMOUNT, ...)`.
- Negative `amount_cents` = expense. Positive = income.

## Categories

- Fixed allowed set: `groceries`, `rent`, `utilities`, `transport`, `dining`,
  `salary`, `other`. Any other category (after alias resolution below)
  raises `LedgerError(E_UNKNOWN_CATEGORY, ...)`.

### Category Aliases

- The following aliases are accepted **wherever a category is taken as
  input** — `add`, `split` shares, and any future category-accepting
  entry point — and resolved to their canonical category before validation
  or storage:

  | Alias   | Canonical    |
  | ------- | ------------ |
  | `food`  | `groceries`  |
  | `car`   | `transport`  |
  | `fuel`  | `transport`  |

- Once resolved, a `Transaction`'s stored `category` is always the
  canonical name — aliases never appear in `Store.transactions`, CLI
  output, statements, or exports.

Related: `mem:dom/DOM_SPLIT_ALLOCATION` (aliases apply to split shares),
`mem:dom/DOM_EXPORT_FORMATS` (exports always show canonical category),
`mem:feature/FEATURE_LEDGER` (module layout), `mem:ref/REF_CLI_OUTPUT`
(CLI formats), `mem:ref/REF_ERROR_CODES` (all new error codes for
statements/exports/splits).
