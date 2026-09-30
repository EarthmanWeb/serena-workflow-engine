# ledgerlite

A minimal personal finance ledger, CLI + library, Python 3.11+ stdlib only.

## Usage

```bash
python3 -m ledgerlite add --date 2026-01-05 --description "Groceries" --amount -45.67 --category groceries
python3 -m ledgerlite list --month 2026-01
python3 -m ledgerlite balance
```

## Data model

Amounts are stored as integer cents (negative = expense, positive = income) to avoid
floating point error. The ledger file is JSON (`ledger.json` by default, override with
`--file`).

## Tests

```bash
python3 -m unittest discover -s tests
```
