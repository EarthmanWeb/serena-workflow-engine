---
name: Export Formats
description: Exact byte-level CSV/JSON export formats and the export audit log. Authoritative — hidden acceptance tests assert on these formats byte-for-byte.
metadata:
  type: domain
---

# DOM_EXPORT_FORMATS — CSV/JSON Export Formats

`export_csv` and `export_json` (and the `export` CLI subcommand) write a
fiscal period's transactions (see `mem:dom/DOM_FISCAL_CALENDAR` for period
bounds) to a file in one of two formats. Neither format matches Python's
library defaults — every deviation below is intentional and graded exactly.

## CSV (`export_csv`)

- **Delimiter**: semicolon (`;`), not comma.
- **Header row** (exact, case-sensitive):
  `id;date;description;category;amount`
- **Date format**: `DD.MM.YYYY` (e.g. `20.01.2026`), not ISO.
- **Amount format**: comma as the decimal separator (e.g. `12,34`), with a
  leading `-` sign for expenses (negative `amount_cents`) and no sign for
  income. Example: `-5,00` for an expense of 5.00, `5,00` for income of the
  same magnitude.
- **Encoding**: UTF-8 **with a BOM** (`\xef\xbb\xbf` at the start of the
  file).
- **Line endings**: CRLF (`\r\n`) for every row, including the header.
- Rows are sorted by transaction date ascending, then id ascending (same
  ordering as `build_statement`'s `lines`).
- `description` is redacted (`mem:dom/DOM_PRIVACY_REDACTION`) and `category`
  is canonicalized (`mem:dom/DOM_LEDGER_RULES`) in every exported row.

## JSON (`export_json`)

- Top-level envelope:
  ```json
  {
    "schema": "ledgerlite.export/3",
    "period": {"start": "<ISO date>", "end": "<ISO date>"},
    "entries": [ {"id": ..., "date": ..., "description": ..., "category": ..., "amount": "12.34"}, ... ]
  }
  ```
- `period.start`/`period.end` are the fiscal period's ISO dates (see
  `mem:dom/DOM_FISCAL_CALENDAR`), not the raw `"YYYY-MM"` string.
- Every object's keys are written **sorted alphabetically** (pass
  `sort_keys=True` to `json.dump`, or equivalent).
- `amount` is a **decimal string** (e.g. `"-5.00"`, `"12.34"`), not a raw
  integer-cents number.
- `description` is redacted and `category` is canonicalized, same as CSV.

## Refusing to Overwrite

- Both export functions take a `force: bool = False` parameter. If the
  destination `path` already exists and `force` is not set, raise
  `LedgerError(E_EXPORT_EXISTS, ...)` and write nothing. `force=True`
  overwrites unconditionally.
- The `export` CLI subcommand exposes this as `--force`.
- An unrecognized `--format` value raises `LedgerError(E_EXPORT_FORMAT, ...)`
  — see `mem:ref/REF_ERROR_CODES`.

## Audit Log

- Every successful export (CSV or JSON) appends exactly one line to
  `.ledgerlite-audit.log`, located in the **same directory as the ledger
  file** (`os.path.dirname(store.path)`), creating the file if it does not
  exist.
- Line format (no trailing extra whitespace beyond the newline):
  ```
  <ISO8601 UTC timestamp>|export|<format>|<period>|<count>
  ```
  - `<format>` is `csv` or `json`.
  - `<period>` is the raw `"YYYY-MM"` string passed in (not the resolved
    fiscal dates).
  - `<count>` is the number of entries written.
- Timestamp source: if the environment variable `LEDGERLITE_NOW` is set,
  use it verbatim as the timestamp (tests set this for determinism).
  Otherwise use the current UTC time formatted as
  `%Y-%m-%dT%H:%M:%SZ`.

Related: `mem:dom/DOM_FISCAL_CALENDAR`, `mem:dom/DOM_PRIVACY_REDACTION`,
`mem:dom/DOM_LEDGER_RULES` (category aliases), `mem:ref/REF_ERROR_CODES`
(E_EXPORT_FORMAT, E_EXPORT_EXISTS), `mem:ref/REF_CLI_OUTPUT`.
