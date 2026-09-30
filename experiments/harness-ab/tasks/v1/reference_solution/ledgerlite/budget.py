"""Monthly category budget reporting."""

import calendar
from dataclasses import dataclass
from datetime import date

from .errors import E_BAD_MONTH, LedgerError
from .recurring import occurrences


@dataclass
class BudgetLine:
    category: str
    limit_cents: int
    spent_cents: int
    remaining_cents: int
    status: str


def validate_month(month: str) -> tuple[int, int]:
    """Validate a "YYYY-MM" month string, returning (year, month) ints."""
    parts = month.split("-")
    if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
        raise LedgerError(E_BAD_MONTH, f"invalid month: {month!r}")
    try:
        year = int(parts[0])
        mon = int(parts[1])
    except ValueError:
        raise LedgerError(E_BAD_MONTH, f"invalid month: {month!r}")
    if mon < 1 or mon > 12:
        raise LedgerError(E_BAD_MONTH, f"invalid month: {month!r}")
    return year, mon


def _status_for(spent_cents: int, limit_cents: int) -> str:
    if limit_cents <= 0:
        ratio = float("inf") if spent_cents > 0 else 0.0
    else:
        ratio = spent_cents / limit_cents
    if ratio > 1.0:
        return "over"
    if ratio >= 0.8:
        return "warning"
    return "ok"


def budget_report(store, month: str) -> list["BudgetLine"]:
    """Compute the budget report for `month` ("YYYY-MM")."""
    year, mon = validate_month(month)
    last_day = calendar.monthrange(year, mon)[1]
    window_start = date(year, mon, 1)
    window_end = date(year, mon, last_day)

    budgets = store.data.get("budgets", {}).get(month, {})

    spent_by_category: dict[str, int] = {}

    for tx in store.transactions:
        if tx.date.year == year and tx.date.month == mon and tx.amount_cents < 0:
            spent_by_category[tx.category] = spent_by_category.get(tx.category, 0) + abs(tx.amount_cents)

    for rule in store.list_recurring():
        if rule.amount_cents >= 0:
            continue
        dates = occurrences(rule, window_start, window_end)
        if dates:
            spent_by_category[rule.category] = spent_by_category.get(rule.category, 0) + abs(
                rule.amount_cents
            ) * len(dates)

    lines = []
    for category in sorted(budgets.keys()):
        limit_cents = budgets[category]
        spent_cents = spent_by_category.get(category, 0)
        remaining_cents = limit_cents - spent_cents
        status = _status_for(spent_cents, limit_cents)
        lines.append(
            BudgetLine(
                category=category,
                limit_cents=limit_cents,
                spent_cents=spent_cents,
                remaining_cents=remaining_cents,
                status=status,
            )
        )
    return lines
