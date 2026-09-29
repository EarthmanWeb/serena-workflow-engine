---
name: Development Standards
description: Project overview and conventions for ledgerlite.
metadata:
  type: feature
---

# FEATURE_DEV_STANDARDS — Development Standards

## Project Overview

`ledgerlite` — minimal personal finance ledger, CLI + library. Python 3.11+,
standard library only (no third-party dependencies, no pip installs).

**Entry points:**
- Library: `ledgerlite/` package.
- CLI: `python3 -m ledgerlite` (`ledgerlite/__main__.py` → `ledgerlite/cli.py:main`).
- Tests: `tests/` (stdlib `unittest`).

## Conventions

- **Money**: always integer cents internally. Use `Decimal` only at the parse/format
  boundary in `ledgerlite/money.py`. Never do arithmetic on floats or raw decimal
  strings elsewhere. Export amount strings (see `mem:dom/DOM_EXPORT_FORMATS`) are
  formatted independently of `money.format_cents` — they use a different
  decimal/sign convention specific to exports.
- **Models**: plain `@dataclass` (see `ledgerlite/models.py`).
- **Errors**: raise `LedgerError(CODE, message)` from `ledgerlite/errors.py` for every
  domain-level validation failure; add new `E_*` constants there rather than raising
  bare exceptions or returning error strings — see `mem:ref/REF_ERROR_CODES` for the
  exact set of new codes required.
- **IDs**: sequential, prefixed (`t1`, `t2`, … for transactions), computed as
  `max(existing numeric suffixes) + 1`. Split children are ordinary transactions and
  consume the same `t`-prefixed id sequence.
- **CLI**: `argparse`-based, `main(argv=None) -> int`. Errors caught at the top level
  and printed as `error: <CODE>: <message>` to stderr with exit code `2` — see
  `mem:ref/REF_CLI_OUTPUT` for exact formats.
- **File organization**: one module per concern (money, errors, categories, models,
  store, split, statement, export, cli); do not merge unrelated responsibilities into
  one file.

## Testing

- See `mem:feature/FEATURE_TESTS`.
- Domain/business rules referenced by tests: `mem:dom/DOM_LEDGER_RULES`,
  `mem:dom/DOM_FISCAL_CALENDAR`, `mem:dom/DOM_SPLIT_ALLOCATION`,
  `mem:dom/DOM_EXPORT_FORMATS`, `mem:dom/DOM_PRIVACY_REDACTION`.
