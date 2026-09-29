"""JSON file persistence for ledgerlite transactions."""

import json
import os
from datetime import date, datetime

from .errors import E_NOT_FOUND, E_UNKNOWN_CATEGORY, LedgerError
from .categories import ALLOWED_CATEGORIES
from .models import Transaction

SCHEMA_VERSION = 1


class Store:
    """Loads/saves a ledger JSON file and provides query operations."""

    def __init__(self, path: str):
        self.path = path
        self.transactions: list[Transaction] = []

    def load(self) -> None:
        """Load transactions from the JSON file at self.path.

        If the file does not exist, starts with an empty transaction list
        (does not raise).
        """
        if not os.path.exists(self.path):
            self.transactions = []
            return
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.transactions = [
            Transaction(
                id=t["id"],
                date=date.fromisoformat(t["date"]),
                description=t["description"],
                amount_cents=t["amount_cents"],
                category=t["category"],
            )
            for t in data.get("transactions", [])
        ]

    def save(self) -> None:
        """Write the current transactions to self.path as JSON."""
        data = {
            "schema_version": SCHEMA_VERSION,
            "transactions": [
                {
                    "id": t.id,
                    "date": t.date.isoformat(),
                    "description": t.description,
                    "amount_cents": t.amount_cents,
                    "category": t.category,
                }
                for t in self.transactions
            ],
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    def _next_id(self) -> str:
        max_n = 0
        for t in self.transactions:
            if t.id.startswith("t") and t.id[1:].isdigit():
                max_n = max(max_n, int(t.id[1:]))
        return f"t{max_n + 1}"

    def add_transaction(
        self,
        tx_date: date,
        description: str,
        amount_cents: int,
        category: str,
    ) -> Transaction:
        """Validate and append a new transaction, returning it."""
        if category not in ALLOWED_CATEGORIES:
            raise LedgerError(E_UNKNOWN_CATEGORY, f"unknown category: {category!r}")
        tx = Transaction(
            id=self._next_id(),
            date=tx_date,
            description=description,
            amount_cents=amount_cents,
            category=category,
        )
        self.transactions.append(tx)
        return tx

    def list_transactions(self, month: str | None = None) -> list[Transaction]:
        """Return transactions, optionally filtered to a "YYYY-MM" month."""
        if month is None:
            return list(self.transactions)
        return [t for t in self.transactions if t.date.strftime("%Y-%m") == month]

    def balance(self) -> int:
        """Return the sum of all transaction amounts, in cents."""
        return sum(t.amount_cents for t in self.transactions)

    def get_transaction(self, tx_id: str) -> Transaction:
        for t in self.transactions:
            if t.id == tx_id:
                return t
        raise LedgerError(E_NOT_FOUND, f"transaction not found: {tx_id!r}")
