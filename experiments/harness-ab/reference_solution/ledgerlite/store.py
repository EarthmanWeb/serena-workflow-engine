"""JSON file persistence for ledgerlite transactions, recurring rules, and budgets."""

import json
import os
import shutil
from datetime import date

from .errors import E_NOT_FOUND, E_UNKNOWN_CATEGORY, LedgerError
from .categories import ALLOWED_CATEGORIES
from .models import Transaction
from .recurring import RecurringRule, validate_rule
from .budget import validate_month

SCHEMA_VERSION = 2


class Store:
    """Loads/saves a ledger JSON file and provides query operations."""

    def __init__(self, path: str):
        self.path = path
        self.transactions: list[Transaction] = []
        self.data: dict = {"recurring": [], "budgets": {}}

    def load(self) -> None:
        """Load transactions, recurring rules, and budgets from the JSON file at
        self.path. If the file does not exist, starts empty.

        Transparently migrates a schema_version 1 file to schema_version 2, writing a
        byte-identical backup to `<path>.v1.bak` first (idempotent: migrating an
        already-v2 file is a no-op).
        """
        if not os.path.exists(self.path):
            self.transactions = []
            self.data = {"recurring": [], "budgets": {}}
            return

        with open(self.path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        was_v1 = raw.get("schema_version") == 1
        if was_v1:
            backup_path = self.path + ".v1.bak"
            shutil.copyfile(self.path, backup_path)
            raw["schema_version"] = 2
            raw.setdefault("recurring", [])
            raw.setdefault("budgets", {})

        self.transactions = [
            Transaction(
                id=t["id"],
                date=date.fromisoformat(t["date"]),
                description=t["description"],
                amount_cents=t["amount_cents"],
                category=t["category"],
            )
            for t in raw.get("transactions", [])
        ]

        self.data = {
            k: v for k, v in raw.items() if k not in ("schema_version", "transactions")
        }
        self.data.setdefault("recurring", [])
        self.data.setdefault("budgets", {})

        if was_v1:
            # Persist the migrated (v2) file now that it has been read into memory.
            self.save()

    def save(self) -> None:
        """Write the current transactions, recurring rules, and budgets to self.path
        as a schema_version 2 JSON document, preserving any unknown top-level keys.
        """
        out = dict(self.data)
        out["schema_version"] = SCHEMA_VERSION
        out["transactions"] = [
            {
                "id": t.id,
                "date": t.date.isoformat(),
                "description": t.description,
                "amount_cents": t.amount_cents,
                "category": t.category,
            }
            for t in self.transactions
        ]
        out.setdefault("recurring", [])
        out.setdefault("budgets", {})
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
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

    # -- Recurring rules -------------------------------------------------

    def _next_recurring_id(self) -> str:
        max_n = 0
        for r in self.data.get("recurring", []):
            rid = r["id"] if isinstance(r, dict) else r.id
            if rid.startswith("r") and rid[1:].isdigit():
                max_n = max(max_n, int(rid[1:]))
        return f"r{max_n + 1}"

    def add_recurring(self, rule: RecurringRule) -> RecurringRule:
        """Validate and persist a recurring rule, assigning its id."""
        if rule.category not in ALLOWED_CATEGORIES:
            raise LedgerError(E_UNKNOWN_CATEGORY, f"unknown category: {rule.category!r}")
        validate_rule(rule.frequency, rule.start, rule.end)
        rule.id = self._next_recurring_id()
        self.data.setdefault("recurring", []).append(
            {
                "id": rule.id,
                "description": rule.description,
                "amount_cents": rule.amount_cents,
                "category": rule.category,
                "frequency": rule.frequency,
                "start": rule.start.isoformat(),
                "end": rule.end.isoformat() if rule.end else None,
            }
        )
        return rule

    def list_recurring(self) -> list[RecurringRule]:
        rules = []
        for r in self.data.get("recurring", []):
            rules.append(
                RecurringRule(
                    id=r["id"],
                    description=r["description"],
                    amount_cents=r["amount_cents"],
                    category=r["category"],
                    frequency=r["frequency"],
                    start=date.fromisoformat(r["start"]),
                    end=date.fromisoformat(r["end"]) if r.get("end") else None,
                )
            )
        rules.sort(key=lambda r: int(r.id[1:]))
        return rules

    # -- Budgets -----------------------------------------------------------

    def set_budget(self, category: str, month: str, limit_cents: int) -> None:
        if category not in ALLOWED_CATEGORIES:
            raise LedgerError(E_UNKNOWN_CATEGORY, f"unknown category: {category!r}")
        validate_month(month)
        budgets = self.data.setdefault("budgets", {})
        budgets.setdefault(month, {})[category] = limit_cents

    def get_budget(self, category: str, month: str) -> int | None:
        validate_month(month)
        return self.data.get("budgets", {}).get(month, {}).get(category)
