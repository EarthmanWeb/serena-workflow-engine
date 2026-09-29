---
name: CLI Output Formats
description: Exact stdout/stderr formats for every ledgerlite CLI subcommand. Authoritative — hidden acceptance tests assert on these formats byte-for-byte.
metadata:
  type: reference
---

# REF_CLI_OUTPUT — Exact CLI Output Formats

All amounts are rendered via `money.format_cents` unless noted otherwise
(export amounts use the export-specific format in
`mem:dom/DOM_EXPORT_FORMATS`). All errors print to stderr as
`error: <CODE>: <message>` and the process returns exit code `2` (see
`ledgerlite/cli.py`'s existing error handling — reuse it for new error
codes, see `mem:ref/REF_ERROR_CODES`).

## `add`

`added <id>: <description> <amount> [<category>]` (existing, unchanged).

## `list [--month YYYY-MM]`

`<id>  <date>  <amount>  <category>  <description>` per transaction, two-space
separated (existing, unchanged).

## `balance`

The formatted balance only (existing, unchanged).

## `split --date D --description S --total A --share CAT=W [--share CAT=W ...]`

On success, print one `added` line per created child transaction, in the
same order `Store.add_split` returns them (alphabetical by category — see
`mem:dom/DOM_SPLIT_ALLOCATION`), using the exact same line format as `add`:

```
added <id>: <description> <amount> [<category>]
```

Each child's `<description>` already includes the `[split i/n]` suffix
(see `mem:dom/DOM_SPLIT_ALLOCATION`) — do not add it again in the CLI
layer.

## `statement --period YYYY-MM`

Print `render_statement(build_statement(store, period))` to stdout
verbatim (see `mem:dom/DOM_FISCAL_CALENDAR` for the exact rendered format:
an `OPENING BALANCE` line, one line per transaction, a `CLOSING BALANCE`
line).

## `export --format csv|json --period YYYY-MM --out PATH [--force]`

On success, print exactly one line:

```
exported <period> (<format>) to <out>
```

Do not print anything else on success. See `mem:dom/DOM_EXPORT_FORMATS`
for the exported file's own format and the audit log side effect.

## Errors

Every new error code (`E_FISCAL_PERIOD`, `E_EXPORT_FORMAT`,
`E_SPLIT_WEIGHTS`, `E_EXPORT_EXISTS` — see `mem:ref/REF_ERROR_CODES`)
follows the existing error-printing convention exactly:
`error: <CODE>: <message>` to stderr, exit code `2`. Do not introduce a
different exit code or output stream for any error.

Related: `mem:dom/DOM_LEDGER_RULES`, `mem:dom/DOM_FISCAL_CALENDAR`,
`mem:dom/DOM_SPLIT_ALLOCATION`, `mem:dom/DOM_EXPORT_FORMATS`,
`mem:ref/REF_ERROR_CODES` (the rules that determine these values).
