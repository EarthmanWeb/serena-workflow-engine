Add split transactions, monthly statements, and CSV/JSON export to
`ledgerlite`.

## 1. Split transactions (`ledgerlite/split.py`, `Store.add_split`)

```python
def allocate(total_cents: int, weights: dict[str, int]) -> dict[str, int]:
    ...
```

`allocate` divides `total_cents` across the categories in `weights`
(category -> positive integer weight), returning one integer cent amount
per category, such that the returned amounts sum to exactly `total_cents`.
Zero, negative, or missing weights are invalid input and must raise
(do not silently drop or zero a category).

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
transactions. An unknown category in `shares` (after any alias resolution)
must raise the same way `Store.add_transaction` already does for an
unknown category.

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
`build_statement` computes the period's transaction lines (every
transaction whose date falls within the resolved period bounds, sorted by
date ascending then id ascending) and opening/closing balances.
`render_statement` renders a `Statement` as text; the rendered text must
include, at minimum, the opening balance, one line per transaction in
`lines` mentioning that transaction's description, and the closing
balance, in that order.

An invalid `"YYYY-MM"` period string (wrong shape, or a month outside
`01`-`12`) must raise the same way for `statement` as it does for
`export` below — see the shared error-condition list in section 5.

## 3. Export (`ledgerlite/export.py`)

```python
def export_csv(store: Store, period: str, path: str, force: bool = False) -> None:
    ...


def export_json(store: Store, period: str, path: str, force: bool = False) -> None:
    ...


def export(store: Store, fmt: str, period: str, path: str, force: bool = False) -> None:
    ...
```

`export_csv`/`export_json` write the given period's transactions to
`path` (CSV or JSON respectively); the written file must exist, be
non-empty, and — for JSON — parse as a JSON object containing an
`"entries"` list with one entry per transaction in the period. `force`
controls whether an existing file at `path` may be overwritten (see the
shared error-condition list in section 5 for the refusal case). `export`
dispatches to `export_csv`/`export_json` by `fmt` (`"csv"` or `"json"`);
any other `fmt` value is an error (section 5).

The CSV file's columns, in order, are: `id`, `date`, `description`,
`category`, `amount`. Every other CSV/JSON formatting detail (the header
row's exact text and separator, date/amount formatting, encoding, line
endings, key ordering, the JSON envelope shape, sensitive-data redaction,
category canonicalization) is not restated here — apply the same rules
this project already applies, project-wide, to every file it writes for
consumption outside the app.

## 4. CLI additions (`ledgerlite/cli.py`)

New subcommands:

- `split --date D --description S --total A --share CAT=W [--share CAT=W ...]`
  (`--share` may repeat; `CAT=W` is `category=integer_weight`). On
  success, print one line per created child transaction, using the same
  line format the existing `add` subcommand already uses for a created
  transaction, one line per child in the order `Store.add_split` returns
  them.
- `statement --period YYYY-MM`. On success, print
  `render_statement(build_statement(store, period))` to stdout verbatim.
- `export --format csv|json --period YYYY-MM --out PATH [--force]`. On
  success, print exactly one line: `exported <period> (<format>) to
  <out>`, and nothing else.

Every new error condition below prints to stderr and exits with the same
status code and message shape the CLI already uses for existing domain
errors (see `ledgerlite/cli.py`'s existing error handling — reuse it,
do not add a second catch site or a different exit code).

## 5. New error codes (`ledgerlite/errors.py`)

Add four new `E_*` constants to `ledgerlite/errors.py`, named the same way
every existing `E_*` constant in that file is already named, raised via
the existing `LedgerError` mechanism for exactly these four conditions:

- An invalid `"YYYY-MM"` period string is passed to `build_statement`,
  `export_csv`, `export_json`, or `export` (wrong shape, or a month
  outside `01`-`12`).
- `export` is called with a `fmt` other than `"csv"` or `"json"`.
- `allocate` (or `Store.add_split`) is given an empty `weights`/`shares`
  mapping, or any weight that is not a positive integer.
- `export_csv`/`export_json`/`export` is called with a `path` that already
  exists and `force` is not set.

## 6. Tests

Add your own unit tests for everything you build (allocation, statement
construction/rendering, store methods, exports, CLI subcommands). Keep all
existing tests passing.

---

Work autonomously: skip approval, don't ask me questions, and continue
through to completion. When finished, reply with a short summary of the
files you changed.
