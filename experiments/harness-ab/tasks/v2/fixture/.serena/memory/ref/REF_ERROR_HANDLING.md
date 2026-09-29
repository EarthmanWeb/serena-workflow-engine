---
name: Error Handling Standard
description: Standing naming scheme for domain error codes, plus the CLI's error output contract. Authoritative — every new error code in this project must be derivable from this scheme.
metadata:
  type: reference
---

# REF_ERROR_HANDLING — Error Code Naming Scheme

Every domain-level validation failure in this project is raised as
`LedgerError(CODE, message)` from `ledgerlite/errors.py` — never a bare
exception, never a returned error string. `CODE` is always a module-level
`E_*` constant added to `ledgerlite/errors.py`, never an inline literal.

## Naming Scheme

Every error code follows the exact shape:

```
E_<AREA>_<CONDITION>
```

- `<AREA>` is one word (all caps, underscore-joined if the area name has
  multiple words) naming the subsystem the failure belongs to. Use the
  subsystem/module name the failing check lives in, e.g. a check that
  lives in the period-resolution logic uses the area word `FISCAL` (the
  domain concept that module implements — see
  `mem:dom/DOM_FINANCE_CALENDAR`); a check in the external-file-writing
  logic uses the area word `EXPORT` (see `mem:ref/REF_DATA_INTERCHANGE`);
  a check in the weighted-distribution logic uses the area word `SPLIT`
  (see `mem:dom/DOM_MONEY_DISTRIBUTION`).
- `<CONDITION>` is one or more words (all caps, underscore-joined)
  describing *what* is wrong, using the same vocabulary the failing
  rule's own specification uses for that condition — e.g. a period string
  that fails `mem:dom/DOM_FINANCE_CALENDAR`'s shape/range check uses the
  condition word `PERIOD`; a request for an output format the writer does
  not support uses the condition word `FORMAT`; a distribution whose
  weights fail `mem:dom/DOM_MONEY_DISTRIBUTION`'s validation uses the
  condition word `WEIGHTS`; a write that refuses to overwrite an existing
  destination (see `mem:ref/REF_DATA_INTERCHANGE`) uses the condition word
  `EXISTS`.
- Do not invent a new area word when an existing one already names the
  right subsystem, and do not reuse one error code's condition for a
  different failure mode.

## CLI Error Contract

- The CLI catches every `LedgerError` at its top level (do not add a
  second catch site) and prints exactly:
  ```
  error: <CODE>: <message>
  ```
  to **stderr**, then returns exit code **2**. Every new error code — with
  no exceptions — follows this exact convention: same stream, same exit
  code, same `error: <CODE>: <message>` shape. Never introduce a
  different exit code or output stream for any domain error.

Related: `mem:dom/DOM_FINANCE_CALENDAR`, `mem:dom/DOM_MONEY_DISTRIBUTION`,
`mem:ref/REF_DATA_INTERCHANGE`, `mem:arch/ARCH_LEDGERLITE`.
