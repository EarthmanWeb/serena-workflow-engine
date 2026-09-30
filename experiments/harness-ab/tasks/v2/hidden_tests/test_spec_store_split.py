"""Spec-level tests for Store.add_split: existence, wiring, basic behavior
directly stated or clearly implied by task.md."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.store import Store


class TestStoreAddSplitSpec(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()

    def test_add_split_creates_multiple_transactions(self):
        children = self.store.add_split(date(2026, 1, 5), "Dinner", -3000, {"dining": 1, "groceries": 1})
        self.assertEqual(len(children), 2)

    def test_add_split_children_persist_in_store(self):
        self.store.add_split(date(2026, 1, 5), "Dinner", -3000, {"dining": 1, "groceries": 1})
        self.assertEqual(len(self.store.transactions), 2)

    def test_add_split_children_saved_and_reloaded(self):
        self.store.add_split(date(2026, 1, 5), "Dinner", -3000, {"dining": 1, "groceries": 1})
        self.store.save()
        reloaded = Store(self.path)
        reloaded.load()
        self.assertEqual(len(reloaded.transactions), 2)

    def test_add_split_total_equals_sum_of_children(self):
        children = self.store.add_split(date(2026, 1, 5), "Dinner", -3000, {"dining": 2, "groceries": 1})
        self.assertEqual(sum(c.amount_cents for c in children), -3000)

    def test_add_split_unknown_category_raises(self):
        from ledgerlite.errors import E_UNKNOWN_CATEGORY, LedgerError

        with self.assertRaises(LedgerError) as cm:
            self.store.add_split(date(2026, 1, 5), "X", -1000, {"bogus": 1})
        self.assertEqual(cm.exception.code, E_UNKNOWN_CATEGORY)

    def test_add_split_children_have_distinct_ids(self):
        children = self.store.add_split(date(2026, 1, 5), "Dinner", -3000, {"dining": 1, "groceries": 1})
        ids = [c.id for c in children]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
