"""Monthly statement rendering, using ledgerlite's fiscal-period calendar."""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from .errors import E_FISCAL_PERIOD, LedgerError
from .money import format_cents

_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")


def fiscal_period_bounds(period: str) -> tuple:
    """Validate a "YYYY-MM" period string and return (period_start, period_end)
    as dates: the 15th of that month through the 14th of the following month,
    inclusive on both ends.

    Raises LedgerError(E_FISCAL_PERIOD) if period is not "YYYY-MM" with a
    valid month 01-12.
    """
    m = _PERIOD_RE.match(period or "")
    if not m:
        raise LedgerError(E_FISCAL_PERIOD, f"invalid period: {period!r}")
    year = int(m.group(1))
    month = int(m.group(2))
    if month < 1 or month > 12:
        raise LedgerError(E_FISCAL_PERIOD, f"invalid period: {period!r}")
    period_start = date(year, month, 15)
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    period_end = date(next_year, next_month, 14)
    return period_start, period_end


@dataclass
class Statement:
    period: str
    period_start: date
    period_end: date
    opening_balance_cents: int
    lines: list = field(default_factory=list)
    closing_balance_cents: int = 0


def build_statement(store, period: str) -> "Statement":
    """Build a Statement for the fiscal `period` ("YYYY-MM").

    opening_balance_cents is the sum of every transaction dated strictly
    before period_start. lines is every transaction within
    [period_start, period_end] (inclusive), sorted by date ascending then id
    ascending. closing_balance_cents = opening_balance_cents + sum(lines).
    """
    period_start, period_end = fiscal_period_bounds(period)

    opening = sum(
        t.amount_cents for t in store.transactions if t.date < period_start
    )
    lines = [
        t
        for t in store.transactions
        if period_start <= t.date <= period_end
    ]
    lines.sort(key=lambda t: (t.date, t.id))
    closing = opening + sum(t.amount_cents for t in lines)

    return Statement(
        period=period,
        period_start=period_start,
        period_end=period_end,
        opening_balance_cents=opening,
        lines=lines,
        closing_balance_cents=closing,
    )


def render_statement(stmt: "Statement") -> str:
    """Render a Statement as text.

    First line: "OPENING BALANCE  <amount>" (two spaces).
    One line per transaction: "<date>  <amount>  <category>  <description>"
    (two-space separated, same field order/format as the `list` CLI command).
    Last line: "CLOSING BALANCE  <amount>" (two spaces).
    """
    out_lines = [f"OPENING BALANCE  {format_cents(stmt.opening_balance_cents)}"]
    for t in stmt.lines:
        out_lines.append(
            f"{t.date.isoformat()}  {format_cents(t.amount_cents)}  {t.category}  {t.description}"
        )
    out_lines.append(f"CLOSING BALANCE  {format_cents(stmt.closing_balance_cents)}")
    return "\n".join(out_lines) + "\n"
