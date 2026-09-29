import os
import tempfile
import unittest
from datetime import date

from ledgerlite.budget import budget_report
from ledgerlite.recurring import RecurringRule
from ledgerlite.store import Store


class TestBudgetReport(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()

    def test_basic_spend_and_remaining(self):
        self.store.add_transaction(date(2026, 1, 5), "groceries run", -3000, "groceries")
        self.store.set_budget("groceries", "2026-01", 10000)
        lines = budget_report(self.store, "2026-01")
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(line.category, "groceries")
        self.assertEqual(line.limit_cents, 10000)
        self.assertEqual(line.spent_cents, 3000)
        self.assertEqual(line.remaining_cents, 7000)
        self.assertEqual(line.status, "ok")

    def test_income_excluded_from_spend(self):
        self.store.add_transaction(date(2026, 1, 5), "paycheck", 500000, "salary")
        self.store.set_budget("salary", "2026-01", 10000)
        lines = budget_report(self.store, "2026-01")
        self.assertEqual(lines[0].spent_cents, 0)
        self.assertEqual(lines[0].status, "ok")

    def test_zero_spend_category_still_appears(self):
        self.store.set_budget("rent", "2026-01", 100000)
        lines = budget_report(self.store, "2026-01")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].spent_cents, 0)
        self.assertEqual(lines[0].status, "ok")

    def test_category_without_budget_not_in_report(self):
        self.store.add_transaction(date(2026, 1, 5), "dinner", -2000, "dining")
        lines = budget_report(self.store, "2026-01")
        self.assertEqual(lines, [])

    def test_sorted_by_category_name(self):
        self.store.set_budget("utilities", "2026-01", 10000)
        self.store.set_budget("dining", "2026-01", 10000)
        self.store.set_budget("groceries", "2026-01", 10000)
        lines = budget_report(self.store, "2026-01")
        self.assertEqual([l.category for l in lines], ["dining", "groceries", "utilities"])

    def test_recurring_included_in_spend(self):
        rule = RecurringRule(
            id="",
            description="rent",
            amount_cents=-150000,
            category="rent",
            frequency="monthly",
            start=date(2026, 1, 1),
        )
        self.store.add_recurring(rule)
        self.store.set_budget("rent", "2026-01", 200000)
        lines = budget_report(self.store, "2026-01")
        self.assertEqual(lines[0].spent_cents, 150000)
        self.assertEqual(lines[0].remaining_cents, 50000)

    def test_recurring_multiple_occurrences_in_month(self):
        rule = RecurringRule(
            id="",
            description="weekly snack",
            amount_cents=-500,
            category="dining",
            frequency="weekly",
            start=date(2026, 1, 1),
        )
        self.store.add_recurring(rule)
        self.store.set_budget("dining", "2026-01", 10000)
        lines = budget_report(self.store, "2026-01")
        # 5 weekly occurrences in Jan 2026 starting Jan 1: 1,8,15,22,29
        self.assertEqual(lines[0].spent_cents, 2500)

    def test_status_boundary_below_80_percent(self):
        self.store.add_transaction(date(2026, 1, 5), "x", -7999, "groceries")
        self.store.set_budget("groceries", "2026-01", 10000)
        lines = budget_report(self.store, "2026-01")
        self.assertEqual(lines[0].status, "ok")

    def test_status_boundary_exactly_80_percent(self):
        self.store.add_transaction(date(2026, 1, 5), "x", -8000, "groceries")
        self.store.set_budget("groceries", "2026-01", 10000)
        lines = budget_report(self.store, "2026-01")
        self.assertEqual(lines[0].status, "warning")

    def test_status_boundary_exactly_100_percent(self):
        self.store.add_transaction(date(2026, 1, 5), "x", -10000, "groceries")
        self.store.set_budget("groceries", "2026-01", 10000)
        lines = budget_report(self.store, "2026-01")
        self.assertEqual(lines[0].status, "warning")

    def test_status_boundary_just_over_100_percent(self):
        self.store.add_transaction(date(2026, 1, 5), "x", -10001, "groceries")
        self.store.set_budget("groceries", "2026-01", 10000)
        lines = budget_report(self.store, "2026-01")
        self.assertEqual(lines[0].status, "over")

    def test_bad_month_raises(self):
        from ledgerlite.errors import E_BAD_MONTH, LedgerError

        with self.assertRaises(LedgerError) as cm:
            budget_report(self.store, "not-a-month")
        self.assertEqual(cm.exception.code, E_BAD_MONTH)


if __name__ == "__main__":
    unittest.main()
