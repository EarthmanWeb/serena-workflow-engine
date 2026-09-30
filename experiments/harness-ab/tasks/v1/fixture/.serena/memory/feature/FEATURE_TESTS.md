---
name: Test Suite
description: Test runner and verification approach for ledgerlite.
metadata:
  type: feature
---

# FEATURE_TESTS — Test Suite

| Property  | Value             |
| --------- | ----------------- |
| Key       | TESTS             |
| Type      | infrastructure    |
| Language  | Python            |
| Framework | unittest (stdlib) |

## Running Tests

Run from the project root:

```bash
python3 -m unittest discover -s tests
```

Run a single file:

```bash
python3 -m unittest tests.test_money -v
```

## Verification

- Unit tests: `python3 -m unittest discover -s tests -p 'test_*.py'`.
- New functional code requires corresponding new tests in `tests/`.
- Never touch the real `ledger.json` in tests — use `tempfile` dirs (see existing
  `tests/test_store.py`, `tests/test_cli.py` for the pattern).

## Task-Completion Checklist

1. `python3 -m unittest discover -s tests` — full suite must be green (existing +
   new tests).
2. Re-read `mem:dom/DOM_LEDGER_RULES` if any validation/threshold logic changed, to
   confirm the implementation still matches the documented rules exactly.
