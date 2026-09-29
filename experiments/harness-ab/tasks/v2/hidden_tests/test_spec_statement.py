"""Spec-level tests for statement.build_statement / render_statement:
existence and basic shape, as stated in task.md (dataclass fields named
exactly, functions exist with the stated signature)."""

import os
import tempfile
import unittest
from dataclasses import fields
from datetime import date

from ledgerlite.statement import Statement, build_statement, render_statement
from ledgerlite.store import Store


class TestStatementSpec(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()

    def test_statement_dataclass_has_required_fields(self):
        names = {f.name for f in fields(Statement)}
        for required in (
            "opening_balance_cents",
            "lines",
            "closing_balance_cents",
            "period_start",
            "period_end",
        ):
            self.assertIn(required, names)

    def test_build_statement_returns_statement(self):
        stmt = build_statement(self.store, "2026-01")
        self.assertIsInstance(stmt, Statement)

    def test_empty_store_zero_balances(self):
        stmt = build_statement(self.store, "2026-01")
        self.assertEqual(stmt.opening_balance_cents, 0)
        self.assertEqual(stmt.closing_balance_cents, 0)
        self.assertEqual(stmt.lines, [])

    def test_closing_balance_reflects_lines(self):
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "other")
        stmt = build_statement(self.store, "2026-01")
        self.assertEqual(stmt.closing_balance_cents, stmt.opening_balance_cents - 500)

    def test_render_statement_returns_string(self):
        stmt = build_statement(self.store, "2026-01")
        rendered = render_statement(stmt)
        self.assertIsInstance(rendered, str)

    def test_render_statement_mentions_transaction_description(self):
        self.store.add_transaction(date(2026, 1, 20), "unique-description-xyz", -500, "other")
        stmt = build_statement(self.store, "2026-01")
        rendered = render_statement(stmt)
        self.assertIn("unique-description-xyz", rendered)


if __name__ == "__main__":
    unittest.main()
