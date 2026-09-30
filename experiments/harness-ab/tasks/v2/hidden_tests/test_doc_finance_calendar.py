"""Doc-only: finance calendar policy (dom/DOM_FINANCE_CALENDAR).
Period "YYYY-MM" runs from the 15th of that month through the 14th of the
next month, inclusive."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.statement import build_statement
from ledgerlite.store import Store


class TestFiscalCalendar(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()

    def test_period_start_is_15th(self):
        stmt = build_statement(self.store, "2026-01")
        self.assertEqual(stmt.period_start, date(2026, 1, 15))

    def test_period_end_is_14th_of_next_month(self):
        stmt = build_statement(self.store, "2026-01")
        self.assertEqual(stmt.period_end, date(2026, 2, 14))

    def test_december_period_rolls_to_next_year(self):
        stmt = build_statement(self.store, "2026-12")
        self.assertEqual(stmt.period_start, date(2026, 12, 15))
        self.assertEqual(stmt.period_end, date(2027, 1, 14))

    def test_transaction_on_14th_belongs_to_prior_period(self):
        self.store.add_transaction(date(2026, 1, 14), "before cutoff", -100, "other")
        stmt = build_statement(self.store, "2026-01")
        self.assertEqual(stmt.lines, [])
        self.assertEqual(stmt.opening_balance_cents, -100)

    def test_transaction_on_15th_belongs_to_period(self):
        self.store.add_transaction(date(2026, 1, 15), "on cutoff", -100, "other")
        stmt = build_statement(self.store, "2026-01")
        self.assertEqual(len(stmt.lines), 1)
        self.assertEqual(stmt.opening_balance_cents, 0)

    def test_transaction_on_last_day_included(self):
        self.store.add_transaction(date(2026, 2, 14), "last day", -100, "other")
        stmt = build_statement(self.store, "2026-01")
        self.assertEqual(len(stmt.lines), 1)

    def test_transaction_on_day_after_period_excluded(self):
        self.store.add_transaction(date(2026, 2, 15), "next period", -100, "other")
        stmt = build_statement(self.store, "2026-01")
        self.assertEqual(stmt.lines, [])


if __name__ == "__main__":
    unittest.main()
