import os
import tempfile
import unittest
from datetime import date

from ledgerlite.errors import E_UNKNOWN_CATEGORY, LedgerError
from ledgerlite.store import Store


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")

    def test_load_missing_file_starts_empty(self):
        store = Store(self.path)
        store.load()
        self.assertEqual(store.transactions, [])

    def test_add_and_save_and_reload(self):
        store = Store(self.path)
        store.load()
        store.add_transaction(date(2026, 1, 5), "Groceries", -1234, "groceries")
        store.save()

        reloaded = Store(self.path)
        reloaded.load()
        self.assertEqual(len(reloaded.transactions), 1)
        tx = reloaded.transactions[0]
        self.assertEqual(tx.id, "t1")
        self.assertEqual(tx.amount_cents, -1234)
        self.assertEqual(tx.category, "groceries")

    def test_add_unknown_category_raises(self):
        store = Store(self.path)
        store.load()
        with self.assertRaises(LedgerError) as cm:
            store.add_transaction(date(2026, 1, 5), "X", -100, "bogus")
        self.assertEqual(cm.exception.code, E_UNKNOWN_CATEGORY)

    def test_ids_increment(self):
        store = Store(self.path)
        store.load()
        t1 = store.add_transaction(date(2026, 1, 1), "A", -100, "other")
        t2 = store.add_transaction(date(2026, 1, 2), "B", -200, "other")
        self.assertEqual(t1.id, "t1")
        self.assertEqual(t2.id, "t2")

    def test_list_transactions_filters_by_month(self):
        store = Store(self.path)
        store.load()
        store.add_transaction(date(2026, 1, 5), "Jan", -100, "other")
        store.add_transaction(date(2026, 2, 5), "Feb", -100, "other")
        jan = store.list_transactions(month="2026-01")
        self.assertEqual(len(jan), 1)
        self.assertEqual(jan[0].description, "Jan")

    def test_balance_sums_all(self):
        store = Store(self.path)
        store.load()
        store.add_transaction(date(2026, 1, 1), "Income", 100000, "salary")
        store.add_transaction(date(2026, 1, 2), "Expense", -2500, "dining")
        self.assertEqual(store.balance(), 97500)

    def test_save_file_format(self):
        import json

        store = Store(self.path)
        store.load()
        store.add_transaction(date(2026, 1, 5), "X", -100, "other")
        store.save()
        with open(self.path) as f:
            data = json.load(f)
        self.assertIn("schema_version", data)
        self.assertIn("transactions", data)
        self.assertEqual(data["transactions"][0]["date"], "2026-01-05")


if __name__ == "__main__":
    unittest.main()
