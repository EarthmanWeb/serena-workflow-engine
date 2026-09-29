"""Data models for ledgerlite."""

from dataclasses import dataclass
from datetime import date


@dataclass
class Transaction:
    """A single ledger transaction.

    amount_cents is signed: negative amounts are expenses, positive
    amounts are income.
    """

    id: str
    date: date
    description: str
    amount_cents: int
    category: str
