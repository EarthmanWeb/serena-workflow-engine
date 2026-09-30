# ledgerlite — project guidance

- Run tests: `python3 -m unittest discover -s tests`
- Python 3.11+, standard library only — no third-party dependencies.
- All monetary amounts are represented as integer cents internally. Parse/format at the
  boundary only (see `ledgerlite/money.py`); never do arithmetic on decimal strings or floats.
- Fixed category set lives in `ledgerlite/categories.py`.
- Domain errors are raised as `LedgerError` (see `ledgerlite/errors.py`) with a stable
  `.code` from the `E_*` constants.
- Project documentation: .serena/memory/ (index: .serena/memory/MEMORY.md)
