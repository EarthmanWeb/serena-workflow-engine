"""Recurring transaction rules and occurrence expansion."""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from .errors import E_BAD_DATE_RANGE, E_BAD_FREQUENCY, LedgerError

FREQUENCIES = frozenset({"weekly", "biweekly", "monthly"})


@dataclass
class RecurringRule:
    id: str
    description: str
    amount_cents: int
    category: str
    frequency: str
    start: date
    end: date | None = None


def validate_rule(frequency: str, start: date, end: date | None) -> None:
    """Validate frequency and date range, raising LedgerError on failure."""
    if frequency not in FREQUENCIES:
        raise LedgerError(E_BAD_FREQUENCY, f"unknown frequency: {frequency!r}")
    if end is not None and end < start:
        raise LedgerError(E_BAD_DATE_RANGE, f"end {end} is before start {start}")


def _monthly_occurrence(start: date, month_index: int) -> date:
    """Return the occurrence date for the month `month_index` months after start.month,
    on start's day-of-month, clamped to that target month's last valid day.
    """
    total_month = (start.year * 12 + (start.month - 1)) + month_index
    year, month0 = divmod(total_month, 12)
    month = month0 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(start.day, last_day)
    return date(year, month, day)


def occurrences(rule: RecurringRule, window_start: date, window_end: date) -> list[date]:
    """Return the ascending list of dates on which `rule` fires within the inclusive
    window [window_start, window_end], respecting rule.start and rule.end.
    """
    results: list[date] = []
    effective_end = window_end
    if rule.end is not None and rule.end < effective_end:
        effective_end = rule.end

    if rule.frequency == "weekly":
        step = timedelta(days=7)
    elif rule.frequency == "biweekly":
        step = timedelta(days=14)
    elif rule.frequency == "monthly":
        step = None
    else:
        raise LedgerError("E_BAD_FREQUENCY", f"unknown frequency: {rule.frequency!r}")

    if step is not None:
        current = rule.start
        while current <= effective_end:
            if current >= window_start and current >= rule.start:
                results.append(current)
            current = current + step
    else:
        month_index = 0
        while True:
            occ = _monthly_occurrence(rule.start, month_index)
            if occ > effective_end:
                break
            if occ >= window_start and occ >= rule.start:
                results.append(occ)
            month_index += 1

    results.sort()
    return results
