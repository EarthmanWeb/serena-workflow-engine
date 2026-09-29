---
name: CLI Output Formats
description: Exact stdout/stderr formats for every ledgerlite CLI subcommand. Authoritative — hidden acceptance tests assert on these formats byte-for-byte.
metadata:
  type: reference
---

# REF_CLI_OUTPUT — Exact CLI Output Formats

All amounts are rendered via `money.format_cents`. All errors print to stderr as
`error: <CODE>: <message>` and the process returns exit code `2` (see
`ledgerlite/cli.py`'s existing error handling — reuse it for new error codes).

## `add`

`added <id>: <description> <amount> [<category>]` (existing, unchanged).

## `list [--month YYYY-MM]`

`<id>  <date>  <amount>  <category>  <description>` per transaction, two-space
separated (existing, unchanged).

## `balance`

The formatted balance only (existing, unchanged).

## `recurring add --description D --amount A --category C --frequency F --start YYYY-MM-DD [--end YYYY-MM-DD]`

On success, print a line analogous to `add`:
`added <id>: <description> <amount> [<category>] (<frequency>)`

## `recurring list`

One line per rule, sorted by id number ascending, fields separated by TWO spaces:

```
<id>  <frequency>  <start>  <amount>  <category>  <description>
```

- `<start>` is ISO format (`YYYY-MM-DD`).
- `<amount>` is `money.format_cents(amount_cents)`.

## `budget set --category C --month YYYY-MM --limit A`

On success, print: `budget set: <category> <month> <limit>` where `<limit>` is the
formatted amount.

## `budget report --month YYYY-MM`

Print a header line, then one line per `BudgetLine` (already sorted by category name
from `budget_report`), fields separated by TWO spaces:

```
CATEGORY  LIMIT  SPENT  REMAINING  STATUS
<category>  <limit>  <spent>  <remaining>  <status>
```

- `<limit>`, `<spent>`, `<remaining>` are all `money.format_cents` of their respective
  cent values (remaining may render with a leading `-`).
- `<status>` is the literal string `ok`, `warning`, or `over`.
- If no budgets are set for the month, print only the header line.

## Errors

Every new error code (`E_BAD_FREQUENCY`, `E_BAD_MONTH`, `E_BAD_DATE_RANGE`) follows the
existing error-printing convention exactly: `error: <CODE>: <message>` to stderr, exit
code `2`. Do not introduce a different exit code or output stream for any error.

Related: `mem:dom/DOM_LEDGER_RULES` (the rules that determine these values).
