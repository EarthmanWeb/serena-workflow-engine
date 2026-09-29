"""Spec-level tests for ledgerlite.retention.purge: fully determined by
prompt.md's stated signature and general behavior -- no doc-only
convention required to pass these."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.errors import LedgerError
from ledgerlite.retention import PurgeResult, purge
from ledgerlite.store import Store


class TestPurgeSpec(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.store_path)
        self.store.load()

    def test_returns_purge_result(self):
        result = purge(self.store, 1, date(2026, 6, 20))
        self.assertIsInstance(result, PurgeResult)

    def test_no_transactions_nothing_archived(self):
        result = purge(self.store, 1, date(2026, 6, 20))
        self.assertEqual(result.archived, 0)
        self.assertEqual(result.kept, 0)
        self.assertIsNone(result.archive_path)

    def test_recent_transaction_kept(self):
        self.store.add_transaction(date(2026, 6, 20), "x", -100, "other")
        result = purge(self.store, 1, date(2026, 6, 20))
        self.assertEqual(result.kept, 1)
        self.assertEqual(result.archived, 0)

    def test_old_transaction_archived(self):
        self.store.add_transaction(date(2020, 1, 1), "old", -100, "other")
        result = purge(self.store, 1, date(2026, 6, 20))
        self.assertEqual(result.archived, 1)
        self.assertEqual(result.kept, 0)
        self.assertIsNotNone(result.archive_path)
        self.assertTrue(os.path.exists(result.archive_path))

    def test_store_persisted_after_purge(self):
        self.store.add_transaction(date(2020, 1, 1), "old", -100, "other")
        self.store.add_transaction(date(2026, 6, 20), "new", -50, "other")
        purge(self.store, 1, date(2026, 6, 20))
        reloaded = Store(self.store_path)
        reloaded.load()
        self.assertEqual(len(reloaded.transactions), 1)
        self.assertEqual(reloaded.transactions[0].description, "new")

    def test_zero_keep_periods_raises(self):
        with self.assertRaises(LedgerError):
            purge(self.store, 0, date(2026, 6, 20))

    def test_negative_keep_periods_raises(self):
        with self.assertRaises(LedgerError):
            purge(self.store, -1, date(2026, 6, 20))

    def test_kept_reflects_final_store_count(self):
        self.store.add_transaction(date(2020, 1, 1), "old", -100, "other")
        self.store.add_transaction(date(2026, 6, 20), "new1", -50, "other")
        self.store.add_transaction(date(2026, 6, 21), "new2", -50, "other")
        result = purge(self.store, 1, date(2026, 6, 20))
        self.assertEqual(result.kept, 2)


if __name__ == "__main__":
    unittest.main()
