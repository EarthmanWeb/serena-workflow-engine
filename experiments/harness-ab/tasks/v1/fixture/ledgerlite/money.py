"""Money parsing/formatting: decimal strings <-> integer cents.

All monetary amounts are stored internally as integer cents to avoid
floating point error. Use Decimal only at the string parsing boundary.
"""

from decimal import Decimal, InvalidOperation

from .errors import E_INVALID_AMOUNT, LedgerError


def parse_amount(text: str) -> int:
    """Parse a decimal amount string (e.g. "12.34", "-5", "0.5") into integer cents.

    Raises LedgerError(E_INVALID_AMOUNT) for anything that is not a valid
    decimal number.
    """
    if text is None:
        raise LedgerError(E_INVALID_AMOUNT, f"invalid amount: {text!r}")
    text = text.strip()
    if not text:
        raise LedgerError(E_INVALID_AMOUNT, f"invalid amount: {text!r}")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise LedgerError(E_INVALID_AMOUNT, f"invalid amount: {text!r}")
    cents = value * 100
    if cents != cents.to_integral_value():
        raise LedgerError(E_INVALID_AMOUNT, f"invalid amount: {text!r}")
    return int(cents.to_integral_value())


def format_cents(cents: int) -> str:
    """Format integer cents as a decimal string with exactly 2 fraction digits."""
    negative = cents < 0
    abs_cents = abs(cents)
    whole, frac = divmod(abs_cents, 100)
    sign = "-" if negative and abs_cents != 0 else ""
    return f"{sign}{whole}.{frac:02d}"
