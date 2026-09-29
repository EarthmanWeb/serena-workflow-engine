---
name: Finance Calendar Policy
description: Standing policy for how this project defines a fiscal period and computes opening/closing balances for any period-scoped feature. Authoritative — read before implementing any feature that groups records by a "YYYY-MM" period.
metadata:
  type: domain
---

# DOM_FINANCE_CALENDAR — Fiscal Period Policy

This project's fiscal calendar does not match the calendar month. Every
current or future feature that accepts a period identifier in `"YYYY-MM"`
form (reports, statements, exports, projections, reconciliations, anything
period-scoped) must resolve that identifier through the rules below —
never through `date(year, month, 1)` and the calendar month's last day.

## Period Bounds

- A period string `"YYYY-MM"` names the fiscal period that starts on the
  15th of that month and ends on the 14th of the following month,
  inclusive on both ends.
  - `period_start` is the 15th day of the named month.
  - `period_end` is the 14th day of the next month (roll the year forward
    by one when the named month is December).
- A period string must match the shape `YYYY-MM` with a month in `01`-`12`.
  Any other shape or an out-of-range month is an invalid period.

## Worked Example (payroll, illustrative only — not this project's domain)

A payroll system labels its pay period `"2026-03"`. Under this policy that
period runs from 2026-03-15 through 2026-04-14 inclusive. A timesheet entry
dated 2026-03-14 belongs to the prior period (`"2026-02"`), not
`"2026-03"`, because the 14th is the boundary day of the period that ends
that day, not the one that starts that month. An entry dated 2026-04-14 is
still inside `"2026-03"` — it is the period's last included day. An entry
dated 2026-04-15 belongs to `"2026-04"`.

## Opening and Closing Balances

- Whenever a period-scoped report computes an opening balance, that
  opening balance is the sum of every record dated strictly before
  `period_start` — every record ever entered before the boundary, not
  merely records "before the 1st of the month."
- A closing balance is the opening balance plus the sum of every record
  whose date falls within `[period_start, period_end]` inclusive.

Related: `mem:arch/ARCH_LEDGERLITE` (module layout), `mem:ref/REF_REPORT_STYLE`
(how a period report is rendered), `mem:ref/REF_ERROR_HANDLING` (the error
raised for an invalid period string), `mem:ref/REF_DATA_INTERCHANGE` (period
bounds used when files are produced for external consumption).
