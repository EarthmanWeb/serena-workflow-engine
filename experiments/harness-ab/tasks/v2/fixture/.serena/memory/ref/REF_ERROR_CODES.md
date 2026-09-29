---
name: Error Codes
description: Exact new error codes and messages for statements/exports/splits. Authoritative — hidden acceptance tests assert on these codes exactly.
metadata:
  type: reference
---

# REF_ERROR_CODES — New Error Codes

All new error codes follow the existing `LedgerError(CODE, message)`
mechanism in `ledgerlite/errors.py` (see `mem:feature/FEATURE_DEV_STANDARDS`)
and the existing CLI error-printing convention (`error: <CODE>: <message>`
to stderr, exit code `2` — see `mem:ref/REF_CLI_OUTPUT`).

| Constant          | Raised when                                                                                                    |
| ----------------- | --------------------------------------------------------------------------------------------------------------- |
| `E_FISCAL_PERIOD`  | A `"YYYY-MM"` period string is malformed or has an out-of-range month (see `mem:dom/DOM_FISCAL_CALENDAR`). Used by `statement` and `export`. |
| `E_EXPORT_FORMAT`  | An export is requested with a format other than `csv` or `json`.                                                |
| `E_SPLIT_WEIGHTS`  | A split's `shares` is empty, or contains a zero/negative/non-integer weight (see `mem:dom/DOM_SPLIT_ALLOCATION`). |
| `E_EXPORT_EXISTS`  | An export's destination path already exists and `--force`/`force=True` was not given (see `mem:dom/DOM_EXPORT_FORMATS`). |

Add these constants to `ledgerlite/errors.py` alongside the existing
`E_INVALID_AMOUNT`, `E_UNKNOWN_CATEGORY`, `E_NOT_FOUND` — do not invent
different names or reuse an existing code for a new failure mode.

Related: `mem:dom/DOM_FISCAL_CALENDAR`, `mem:dom/DOM_SPLIT_ALLOCATION`,
`mem:dom/DOM_EXPORT_FORMATS`, `mem:ref/REF_CLI_OUTPUT`.
