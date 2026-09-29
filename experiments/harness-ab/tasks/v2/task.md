Add split transactions, monthly statements, and CSV/JSON export to
`ledgerlite`.

## 1. Split transactions (`ledgerlite/split.py`, `Store.add_split`)

```python
def allocate(total_cents: int, weights: dict[str, int]) -> dict[str, int]:
    ...
```

`allocate` divides `total_cents` across the categories in `weights`
(category -> positive integer weight), returning one integer cent amount
per category. Zero, negative, or missing weights are invalid input.

Add to `Store`:

```python
def add_split(
    self,
    tx_date: date,
    description: str,
    total_cents: int,
    shares: dict[str, int],
) -> list[Transaction]:
    ...
```

`add_split` allocates `total_cents` across `shares` via `allocate` and
creates one linked child `Transaction` per category, returning the created
transactions.

## 2. Monthly statement (`ledgerlite/statement.py`)

```python
@dataclass
class Statement:
    period: str
    period_start: date
    period_end: date
    opening_balance_cents: int
    lines: list[Transaction]
    closing_balance_cents: int


def build_statement(store: Store, period: str) -> Statement:
    ...


def render_statement(stmt: Statement) -> str:
    ...
```

`period` is a `"YYYY-MM"` string identifying a statement period.
`build_statement` computes the period's transaction lines and opening/
closing balances. `render_statement` renders a `Statement` as text.

## 3. Export (`ledgerlite/export.py`)

```python
def export_csv(store: Store, period: str, path: str, force: bool = False) -> None:
    ...


def export_json(store: Store, period: str, path: str, force: bool = False) -> None:
    ...
```

Both write the given period's transactions to `path` (CSV or JSON
respectively). `force` controls whether an existing file at `path` may be
overwritten.

## 4. CLI additions (`ledgerlite/cli.py`)

New subcommands:

- `split --date D --description S --total A --share CAT=W [--share CAT=W ...]`
  (`--share` may repeat; `CAT=W` is `category=integer_weight`)
- `statement --period YYYY-MM`
- `export --format csv|json --period YYYY-MM --out PATH [--force]`

## 5. New error codes (`ledgerlite/errors.py`)

Add `E_FISCAL_PERIOD`, `E_EXPORT_FORMAT`, `E_SPLIT_WEIGHTS`,
`E_EXPORT_EXISTS`, raised via the existing `LedgerError` mechanism wherever
validation fails.

## 6. Tests

Add your own unit tests for everything you build (allocation, statement
construction/rendering, store methods, exports, CLI subcommands). Keep all
existing tests passing.

---

Work autonomously: skip approval, don't ask me questions, and continue
through to completion. When finished, reply with a short summary of the
files you changed.
