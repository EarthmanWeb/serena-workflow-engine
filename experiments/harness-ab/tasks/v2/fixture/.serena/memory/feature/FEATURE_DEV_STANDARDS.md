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
  strings elsewhere. Any amount formatting for a file produced for consumption
  outside the app follows a separate, standard-driven format (see
  `mem:ref/REF_DATA_INTERCHANGE`), independent of `money.format_cents`.
- **Models**: plain `@dataclass` (see `ledgerlite/models.py`).
- **Errors**: raise `LedgerError(CODE, message)` from `ledgerlite/errors.py` for every
  domain-level validation failure; add new `E_*` constants there rather than raising
  bare exceptions or returning error strings — see `mem:ref/REF_ERROR_HANDLING` for the
  naming scheme new codes must follow.
- **IDs**: sequential, prefixed (`t1`, `t2`, … for transactions), computed as
  `max(existing numeric suffixes) + 1`. Any derived/child records a feature creates are
  ordinary transactions and consume the same `t`-prefixed id sequence.
- **CLI**: `argparse`-based, `main(argv=None) -> int`. Errors caught at the top level
  and printed as `error: <CODE>: <message>` to stderr with exit code `2` — see
  `mem:ref/REF_ERROR_HANDLING`.
- **File organization**: one module per concern; do not merge unrelated
  responsibilities into one file (see `mem:arch/ARCH_LEDGERLITE` for the current module
  list and layering rule).
- **Module docstrings**: every module's first statement is a one-line docstring
  naming that module's single responsibility (e.g. `"""JSON file persistence for
  ledgerlite transactions."""`) — no blank module, no multi-paragraph module
  docstring duplicating what belongs in a function's own docstring.

## Testing

- See `mem:feature/FEATURE_TESTS`.
- Domain/business rules referenced by tests: `mem:dom/DOM_LEDGER_RULES`,
  `mem:dom/DOM_FINANCE_CALENDAR`, `mem:dom/DOM_MONEY_DISTRIBUTION`,
  `mem:ref/REF_DATA_INTERCHANGE`, `mem:dom/DOM_PRIVACY`,
  `mem:dom/DOM_INPUT_NORMALIZATION`, `mem:dom/DOM_AUDIT`,
  `mem:ref/REF_REPORT_STYLE`.
