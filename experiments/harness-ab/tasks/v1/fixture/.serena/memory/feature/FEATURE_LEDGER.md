---
name: Ledger Feature
description: Architecture of the ledgerlite CLI/library — modules, data flow, file layout.
metadata:
  type: feature
---

# FEATURE_LEDGER — ledgerlite Architecture

| Property     | Value                       |
| ------------ | ---------------------------- |
| Key          | LEDGER                       |
| Type         | Library + CLI                |
| Language     | Python 3.11+ (stdlib only)    |

## Modules

| Module                     | Responsibility                                        |
| --------------------------- | ------------------------------------------------------ |
| `ledgerlite/money.py`        | Parse decimal strings to integer cents / format back    |
| `ledgerlite/errors.py`       | `LedgerError` + `E_*` error code constants               |
| `ledgerlite/categories.py`   | Fixed allowed category set                               |
| `ledgerlite/models.py`       | `Transaction` dataclass                                  |
| `ledgerlite/store.py`        | JSON file persistence + queries (`Store`)                 |
| `ledgerlite/cli.py`          | argparse CLI, `main(argv=None) -> int`                    |
| `ledgerlite/__main__.py`     | `python3 -m ledgerlite` entry point                        |

## Data Flow

CLI (`cli.py`) parses args → calls `Store` methods (`store.py`) → `Store` validates and
mutates in-memory `Transaction` list (`models.py`) → `Store.save()` persists to the JSON
ledger file. All money crosses the CLI/store boundary as integer cents; only `money.py`
touches `Decimal` or user-facing decimal strings.

## File Layout

- Ledger data file: JSON, default path `ledger.json`, overridable via `--file`.
- Format: `{"schema_version": N, "transactions": [...]}` with dates as ISO strings.

## Related Memories

- `mem:dom/DOM_LEDGER_RULES` — domain validation rules, error codes, and business logic
  constraints. READ BEFORE modifying or extending any domain logic (amounts, categories,
  recurring rules, budgets, migrations).
- `mem:ref/REF_CLI_OUTPUT` — exact CLI output formats (stdout/stderr), required for any
  CLI subcommand work.
- `mem:feature/FEATURE_TESTS` — how to run the test suite.
- `mem:feature/FEATURE_DEV_STANDARDS` — language/style conventions.
