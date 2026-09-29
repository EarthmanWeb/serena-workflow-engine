---
name: Ledgerlite Architecture
description: Architecture of the ledgerlite CLI/library — modules, data flow, file layout, and links to the standing standards that apply to all features built on it.
metadata:
  type: architecture
---

# ARCH_LEDGERLITE — ledgerlite Architecture

| Property     | Value                       |
| ------------ | ---------------------------- |
| Key          | LEDGER                       |
| Type         | Library + CLI                |
| Language     | Python 3.11+ (stdlib only)    |

## Layering

`cli` → domain/feature modules → `store` → `models`. Each layer only calls
downward: the CLI parses arguments and formats output but holds no domain
logic itself; feature modules implement one concern each and depend on
`store`/`models`; `store` owns persistence and is the only place that
touches the ledger file; `models` holds plain data shapes with no
behavior. Do not let a feature module reach past `store` into raw file
I/O, and do not put domain validation in the CLI layer.

## Modules

| Module                     | Responsibility                                         |
| --------------------------- | -------------------------------------------------------- |
| `ledgerlite/money.py`        | Parse decimal strings to integer cents / format back      |
| `ledgerlite/errors.py`       | `LedgerError` + `E_*` error code constants                 |
| `ledgerlite/categories.py`   | Fixed allowed category set + input aliases                  |
| `ledgerlite/models.py`       | Data model dataclasses (e.g. `Transaction`)                 |
| `ledgerlite/store.py`        | JSON file persistence + queries (`Store`)                   |
| `ledgerlite/cli.py`          | argparse CLI, `main(argv=None) -> int`                       |
| `ledgerlite/__main__.py`     | `python3 -m ledgerlite` entry point                          |

New feature modules (allocation/distribution logic, period-scoped reports,
external-file export, and anything added after this memory was written)
each get their own file under `ledgerlite/`, named for the concern they
implement, following the same layering rule above.

## Data Flow

CLI (`cli.py`) parses args → calls the relevant feature/`store` functions
→ `Store` validates and mutates the in-memory record list (`models.py`) →
`Store.save()` persists to the JSON ledger file. All money crosses the
CLI/store boundary as integer cents; only `money.py` touches `Decimal` or
user-facing decimal strings for the app's own interactive formatting — any
export-specific decimal/sign formatting for files leaving the app is a
separate, standard-driven format (see `mem:ref/REF_DATA_INTERCHANGE`), not
`money.format_cents`.

## File Layout

- Primary data file: JSON, default path `ledger.json`, overridable via
  `--file`.
- Format: `{"schema_version": N, "transactions": [...]}` with dates as ISO
  strings.
- Any audit trail this project writes lives next to the primary data
  file — see `mem:dom/DOM_AUDIT`.

## Standing Standards (apply to all features, current and future)

These memories are not tied to any one feature — read the relevant ones
before building anything that touches their subject matter:

- `mem:dom/DOM_FINANCE_CALENDAR` — fiscal period bounds for any
  period-scoped feature. READ BEFORE implementing anything that accepts a
  `"YYYY-MM"` period.
- `mem:dom/DOM_MONEY_DISTRIBUTION` — weighted-distribution algorithm and
  derived-record naming. READ BEFORE implementing anything that divides an
  amount across recipients by weight.
- `mem:ref/REF_DATA_INTERCHANGE` — exact CSV/JSON format for any file
  produced for consumption outside the app. READ BEFORE implementing any
  export/report-to-file feature.
- `mem:dom/DOM_PRIVACY` — redaction rules for outbound data. READ BEFORE
  implementing any export/report-to-file feature.
- `mem:dom/DOM_INPUT_NORMALIZATION` — category alias acceptance on input.
  READ BEFORE adding any new category-accepting entry point.
- `mem:ref/REF_ERROR_HANDLING` — error code naming scheme and CLI error
  contract. READ BEFORE adding any new validation failure.
- `mem:dom/DOM_AUDIT` — audit-log policy for writes outside the primary
  data store. READ BEFORE implementing any feature that writes an external
  file.
- `mem:ref/REF_REPORT_STYLE` — text-report rendering conventions. READ
  BEFORE implementing any feature that renders a report as text.
- `mem:feature/FEATURE_TESTS` — how to run the test suite.
- `mem:feature/FEATURE_DEV_STANDARDS` — language/style conventions.

## Related Memories

- `mem:dom/DOM_LEDGER_RULES` — core transaction validation rules (amount
  parsing, the fixed category set).
