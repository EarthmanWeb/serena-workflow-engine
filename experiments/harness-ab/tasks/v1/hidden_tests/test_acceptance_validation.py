import os
import tempfile
import unittest
from datetime import date

from ledgerlite.errors import E_BAD_DATE_RANGE, E_BAD_FREQUENCY, E_BAD_MONTH, LedgerError
from ledgerlite.recurring import RecurringRule
from ledgerlite.store import Store


class TestValidation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()

    def test_bad_frequency_raises(self):
        rule = RecurringRule(
            id="",
            description="x",
            amount_cents=-100,
            category="rent",
            frequency="daily",
            start=date(2026, 1, 1),
        )
        with self.assertRaises(LedgerError) as cm:
            self.store.add_recurring(rule)
        self.assertEqual(cm.exception.code, E_BAD_FREQUENCY)

    def test_bad_date_range_raises(self):
        rule = RecurringRule(
            id="",
            description="x",
            amount_cents=-100,
            category="rent",
            frequency="monthly",
            start=date(2026, 2, 1),
            end=date(2026, 1, 1),
        )
        with self.assertRaises(LedgerError) as cm:
            self.store.add_recurring(rule)
        self.assertEqual(cm.exception.code, E_BAD_DATE_RANGE)

    def test_valid_frequencies_accepted(self):
        for freq in ("weekly", "biweekly", "monthly"):
            rule = RecurringRule(
                id="",
                description="x",
                amount_cents=-100,
                category="rent",
                frequency=freq,
                start=date(2026, 1, 1),
            )
            self.store.add_recurring(rule)  # should not raise

    def test_bad_month_raises_on_budget_set(self):
        with self.assertRaises(LedgerError) as cm:
            self.store.set_budget("rent", "2026-13", 10000)
        self.assertEqual(cm.exception.code, E_BAD_MONTH)

    def test_bad_month_format_raises(self):
        with self.assertRaises(LedgerError) as cm:
            self.store.set_budget("rent", "2026/01", 10000)
        self.assertEqual(cm.exception.code, E_BAD_MONTH)

    def test_bad_month_zero_raises(self):
        with self.assertRaises(LedgerError) as cm:
            self.store.set_budget("rent", "2026-00", 10000)
        self.assertEqual(cm.exception.code, E_BAD_MONTH)

    def test_valid_month_accepted(self):
        self.store.set_budget("rent", "2026-01", 10000)  # should not raise


if __name__ == "__main__":
    unittest.main()
