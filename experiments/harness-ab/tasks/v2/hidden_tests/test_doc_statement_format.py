"""Doc-only: statement rendering and opening-balance rules
(dom/DOM_FISCAL_CALENDAR)."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.statement import build_statement, render_statement
from ledgerlite.store import Store


class TestStatementFormat(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()

    def test_opening_balance_is_sum_before_period_start(self):
        self.store.add_transaction(date(2025, 12, 1), "old1", -100, "other")
        self.store.add_transaction(date(2026, 1, 1), "old2", 500, "salary")
        stmt = build_statement(self.store, "2026-01")
        self.assertEqual(stmt.opening_balance_cents, 400)

    def test_render_first_line_is_opening_balance_label(self):
        stmt = build_statement(self.store, "2026-01")
        rendered = render_statement(stmt)
        first_line = rendered.splitlines()[0]
        self.assertEqual(first_line, "OPENING BALANCE  0.00")

    def test_render_last_line_is_closing_balance_label(self):
        stmt = build_statement(self.store, "2026-01")
        rendered = render_statement(stmt)
        last_line = [l for l in rendered.splitlines() if l][-1]
        self.assertEqual(last_line, "CLOSING BALANCE  0.00")

    def test_render_opening_balance_reflects_prior_transactions(self):
        self.store.add_transaction(date(2026, 1, 1), "prior", -2500, "other")
        stmt = build_statement(self.store, "2026-01")
        rendered = render_statement(stmt)
        self.assertEqual(rendered.splitlines()[0], "OPENING BALANCE  -25.00")

    def test_closing_balance_accounts_for_opening(self):
        self.store.add_transaction(date(2026, 1, 1), "prior", -1000, "other")
        self.store.add_transaction(date(2026, 1, 20), "in-period", -500, "other")
        stmt = build_statement(self.store, "2026-01")
        self.assertEqual(stmt.closing_balance_cents, -1500)


if __name__ == "__main__":
    unittest.main()
