---
name: Development Standards
description: Project overview and conventions for ledgerlite.
metadata:
  type: feature
---

# FEATURE_DEV_STANDARDS — Development Standards

## Project Overview

`ledgerlite` — minimal personal finance ledger, CLI + library. Python 3.11+, standard
library only (no third-party dependencies, no pip installs).

**Entry points:**

- Library: `ledgerlite/` package.
- CLI: `python3 -m ledgerlite` (`ledgerlite/__main__.py` → `ledgerlite/cli.py:main`).
- Tests: `tests/` (stdlib `unittest`).

## Conventions

- **Money**: always integer cents internally. Use `Decimal` only at the parse/format
  boundary in `ledgerlite/money.py`. Never do arithmetic on floats or raw decimal
  strings elsewhere.
- **Models**: plain `@dataclass` (see `ledgerlite/models.py`).
- **Errors**: raise `LedgerError(CODE, message)` from `ledgerlite/errors.py` for every
  domain-level validation failure; add new `E_*` constants there rather than raising
  bare exceptions or returning error strings.
- **IDs**: sequential, prefixed (`t1`, `t2`, … for transactions; `r1`, `r2`, … for
  recurring rules), computed as `max(existing numeric suffixes) + 1`.
- **CLI**: `argparse`-based, `main(argv=None) -> int`. Errors caught at the top level
  and printed as `error: <CODE>: <message>` to stderr with exit code `2` — see
  `mem:ref/REF_CLI_OUTPUT` for exact formats.
- **File organization**: one module per concern (money, errors, categories, models,
  store, cli); do not merge unrelated responsibilities into one file.

## Testing

- See `mem:feature/FEATURE_TESTS`.
- Domain/business rules referenced by tests: `mem:dom/DOM_LEDGER_RULES`.
