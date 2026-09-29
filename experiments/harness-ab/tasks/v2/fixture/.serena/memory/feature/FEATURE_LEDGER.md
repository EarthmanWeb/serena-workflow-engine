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
| `ledgerlite/categories.py`   | Fixed allowed category set + input aliases                |
| `ledgerlite/models.py`       | `Transaction` dataclass                                  |
| `ledgerlite/store.py`        | JSON file persistence + queries (`Store`)                 |
| `ledgerlite/split.py`        | Split-transaction allocation (`allocate`)                 |
| `ledgerlite/statement.py`    | Fiscal-period statements (`Statement`, `build_statement`, `render_statement`) |
| `ledgerlite/export.py`       | CSV/JSON export + redaction + audit log                   |
| `ledgerlite/cli.py`          | argparse CLI, `main(argv=None) -> int`                     |
| `ledgerlite/__main__.py`     | `python3 -m ledgerlite` entry point                        |

## Data Flow

CLI (`cli.py`) parses args → calls `Store`/`split`/`statement`/`export`
functions → `Store` validates and mutates in-memory `Transaction` list
(`models.py`) → `Store.save()` persists to the JSON ledger file. All money
crosses the CLI/store boundary as integer cents; only `money.py` touches
`Decimal` or user-facing decimal strings (export amount formatting is a
separate, export-specific string format — see `mem:dom/DOM_EXPORT_FORMATS`).

## File Layout

- Ledger data file: JSON, default path `ledger.json`, overridable via
  `--file`.
- Format: `{"schema_version": N, "transactions": [...]}` with dates as ISO
  strings.
- Export audit log: `.ledgerlite-audit.log`, next to the ledger file (see
  `mem:dom/DOM_EXPORT_FORMATS`).

## Related Memories

- `mem:dom/DOM_LEDGER_RULES` — domain validation rules, category aliases,
  error codes. READ BEFORE modifying or extending any domain logic.
- `mem:dom/DOM_FISCAL_CALENDAR` — fiscal period bounds used by statements
  and exports. READ BEFORE implementing `statement` or `export`.
- `mem:dom/DOM_SPLIT_ALLOCATION` — split allocation algorithm and child
  naming. READ BEFORE implementing `split`.
- `mem:dom/DOM_EXPORT_FORMATS` — exact CSV/JSON export formats and audit
  log. READ BEFORE implementing `export`.
- `mem:dom/DOM_PRIVACY_REDACTION` — description redaction rules for
  exports. READ BEFORE implementing `export`.
- `mem:ref/REF_ERROR_CODES` — exact new error codes for statements,
  exports, and splits.
- `mem:ref/REF_CLI_OUTPUT` — exact CLI output formats (stdout/stderr),
  required for any CLI subcommand work.
- `mem:feature/FEATURE_TESTS` — how to run the test suite.
- `mem:feature/FEATURE_DEV_STANDARDS` — language/style conventions.
