---
name: Report Style Guide
description: Standing text-report rendering conventions (opening/closing balance lines, per-record line layout) shared by every report this project renders as plain text. Authoritative — hidden acceptance tests assert on this exactly.
metadata:
  type: reference
---

# REF_REPORT_STYLE — Text Report Rendering Conventions

Any feature that renders a period-scoped report as plain text (to stdout
or to a string) — a statement, a summary, any future text report — follows
these layout conventions, so every text report in this project reads the
same way.

## Structure

- The **first line** of a period report is the opening-balance line,
  formatted exactly:
  ```
  OPENING BALANCE  <amount>
  ```
  (the literal label `OPENING BALANCE`, then exactly two spaces, then the
  amount formatted the same way this project's `money` module formats
  amounts everywhere else).
- One line per record follows, in the record's natural project-wide list
  order (see `mem:arch/ARCH_LEDGERLITE`), formatted exactly:
  ```
  <date>  <amount>  <category>  <description>
  ```
  (ISO date, two spaces, formatted amount, two spaces, category, two
  spaces, description — the same field order and two-space separation the
  project's existing `list` output already uses; a report is never a new
  format for the same fields).
- The **last line** is the closing-balance line, formatted exactly:
  ```
  CLOSING BALANCE  <amount>
  ```
  (same label/spacing convention as the opening-balance line).
- A report with zero records still renders both the opening and closing
  balance lines — those two lines are never omitted.

Related: `mem:dom/DOM_FINANCE_CALENDAR` (the balances and lines a period
report renders), `mem:arch/ARCH_LEDGERLITE`.
