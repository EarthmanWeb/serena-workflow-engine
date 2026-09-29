---
name: Fiscal Calendar
description: Fiscal-period boundaries used by statements, exports, and any other period-scoped ledgerlite feature. Authoritative — hidden acceptance tests grade against these boundaries exactly.
metadata:
  type: domain
---

# DOM_FISCAL_CALENDAR — Fiscal Period Boundaries

ledgerlite's fiscal period does NOT match the calendar month. Any feature
that takes a `period` (a `"YYYY-MM"` string) — statements, exports, future
reporting — must resolve it through these bounds, not `date(year, month, 1)`
through the last calendar day.

## Period Bounds

- A period string `"YYYY-MM"` covers **the 15th of that month through the
  14th of the following month**, inclusive on both ends.
  - `period_start` = `date(year, month, 15)`.
  - `period_end` = the 14th of the next month (roll `year` forward when
    `month == 12`).
- Validate the `"YYYY-MM"` shape and month range `01`-`12` exactly as
  existing month validation elsewhere in the project does. An invalid period
  string raises `LedgerError(E_FISCAL_PERIOD, ...)` — see
  `mem:ref/REF_ERROR_CODES`.

## Examples

- Period `"2026-01"` → `2026-01-15` through `2026-02-14` inclusive.
- Period `"2026-12"` → `2026-12-15` through `2027-01-14` inclusive.
- A transaction dated `2026-01-14` belongs to the **prior** period
  (`"2025-12"`), not `"2026-01"`.
- A transaction dated `2026-02-14` still belongs to `"2026-01"` (the last
  day of that period).

## Opening/Closing Balance

- A statement's `opening_balance_cents` is the sum of every transaction
  dated **strictly before** `period_start` — never "before the 1st of the
  month."
- `closing_balance_cents` = `opening_balance_cents` + sum of every
  transaction within `[period_start, period_end]`.

Related: `mem:feature/FEATURE_LEDGER` (module layout),
`mem:ref/REF_CLI_OUTPUT` (exact `statement`/`export` CLI formats),
`mem:ref/REF_ERROR_CODES` (E_FISCAL_PERIOD).
