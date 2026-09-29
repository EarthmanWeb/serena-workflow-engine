Add recurring transactions, monthly category budgets, and a schema v2 migration to
`ledgerlite`.

## 1. Recurring transactions (`ledgerlite/recurring.py`)

```python
@dataclass
class RecurringRule:
    id: str
    description: str
    amount_cents: int
    category: str
    frequency: str
    start: date
    end: date | None = None


def occurrences(rule: RecurringRule, window_start: date, window_end: date) -> list[date]:
    ...
```

`occurrences` returns the dates (ascending) on which `rule` fires within the inclusive
window `[window_start, window_end]`. Validation of `frequency` and of `end` vs `start`
happens when the rule is created (see `Store.add_recurring` below), not inside
`occurrences`.

## 2. Monthly category budgets (`ledgerlite/budget.py`)

```python
@dataclass
class BudgetLine:
    category: str
    limit_cents: int
    spent_cents: int
    remaining_cents: int
    status: str


def budget_report(store: Store, month: str) -> list[BudgetLine]:
    ...
```

`budget_report` computes spend per category for `month` (a `"YYYY-MM"` string),
including amounts contributed by expanding every recurring rule's occurrences that fall
in that month, and returns one `BudgetLine` per category that has a budget set for that
month.

## 3. Store additions (`ledgerlite/store.py`)

Add to `Store`:

- `add_recurring(rule: RecurringRule) -> RecurringRule`
- `list_recurring() -> list[RecurringRule]`
- `set_budget(category: str, month: str, limit_cents: int) -> None`
- `get_budget(category: str, month: str) -> int | None`

The on-disk ledger file format moves to schema v2 to hold recurring rules and budgets
alongside transactions. `Store.load()` must transparently migrate an existing
schema v1 file to v2 the first time it is loaded.

## 4. CLI additions (`ledgerlite/cli.py`)

New subcommands:

- `recurring add --description D --amount A --category C --frequency F --start YYYY-MM-DD [--end YYYY-MM-DD]`
- `recurring list`
- `budget set --category C --month YYYY-MM --limit A`
- `budget report --month YYYY-MM`

## 5. New error codes (`ledgerlite/errors.py`)

Add `E_BAD_FREQUENCY`, `E_BAD_MONTH`, `E_BAD_DATE_RANGE`, raised via the existing
`LedgerError` mechanism wherever validation fails.

## 6. Domain rules and output formats

Validation details (which frequencies are valid, how monthly occurrences land on
short months, budget status thresholds, what counts as "spent", the exact schema v2
migration behavior, and the exact CLI output format for every new subcommand) are
**the project's documented domain rules** — consult the project's Serena memories
before implementing, and implement exactly what they specify. Do not guess or
improvise where a rule is already documented.

## 7. Tests

Add your own unit tests for everything you build (occurrences, budget math, store
methods, CLI subcommands, migration). Keep all existing tests passing.

---

Work autonomously: skip approval, don't ask me questions, and continue through to
completion. When finished, reply with a short summary of the files you changed.
