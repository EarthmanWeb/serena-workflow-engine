"""Doc-only: archival policy (dom/DOM_ARCHIVAL) -- archive file naming
"<store stem>.archive.<fiscal-year>.json" next to the active store,
current fiscal period never archived, append-merge with date-then-id
sort and no duplicate ids across merges."""

import json
import os
import tempfile
import unittest
from datetime import date

from ledgerlite.retention import purge
from ledgerlite.store import Store


class TestArchiveNaming(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.store_path)
        self.store.load()

    def test_archive_filename_uses_store_stem_and_fiscal_year(self):
        self.store.add_transaction(date(2025, 3, 1), "old", -100, "other")
        result = purge(self.store, 1, date(2026, 6, 20))
        expected = os.path.join(self.tmpdir, "ledger.archive.2025.json")
        self.assertEqual(result.archive_path, expected)

    def test_records_spanning_two_fiscal_years_split_into_two_files(self):
        # 2025-06-20 -> fiscal year 2025; 2024-06-20 -> fiscal year 2024
        self.store.add_transaction(date(2025, 6, 20), "a", -100, "other")
        self.store.add_transaction(date(2024, 6, 20), "b", -100, "other")
        purge(self.store, 1, date(2026, 6, 20))
        path_2025 = os.path.join(self.tmpdir, "ledger.archive.2025.json")
        path_2024 = os.path.join(self.tmpdir, "ledger.archive.2024.json")
        self.assertTrue(os.path.exists(path_2025))
        self.assertTrue(os.path.exists(path_2024))

class TestCurrentPeriodNeverArchived(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.store_path)
        self.store.load()

    def test_current_fiscal_period_transaction_never_archived_even_with_keep_1(self):
        self.store.add_transaction(date(2026, 6, 20), "today-tx", -100, "other")
        result = purge(self.store, 1, date(2026, 6, 20))
        self.assertEqual(result.archived, 0)
        self.assertEqual(result.kept, 1)


class TestArchiveAppendMerge(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.store_path)
        self.store.load()

    def test_second_purge_run_merges_into_existing_archive(self):
        # Same store, grown and purged twice: the archive accumulates
        # records across runs rather than being replaced. A still-kept
        # transaction is left in the store between runs so the second
        # run's archived record gets a distinct id (ids are assigned from
        # the store's own current high-water mark).
        self.store.add_transaction(date(2020, 3, 1), "first", -100, "other")
        self.store.add_transaction(date(2026, 6, 20), "keeper", -1, "other")
        result1 = purge(self.store, 1, date(2026, 6, 20))
        self.assertEqual(result1.kept, 1)

        store2 = Store(self.store_path)
        store2.load()
        store2.add_transaction(date(2020, 3, 20), "second", -200, "other")
        result2 = purge(store2, 1, date(2026, 6, 20))

        self.assertEqual(result1.archive_path, result2.archive_path)
        with open(result2.archive_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data["entries"]), 2)

    def test_archive_entries_sorted_by_date_then_id(self):
        self.store.add_transaction(date(2020, 1, 5), "b", -100, "other")
        self.store.add_transaction(date(2020, 1, 1), "a", -100, "other")
        result = purge(self.store, 1, date(2026, 6, 20))
        with open(result.archive_path, encoding="utf-8") as f:
            data = json.load(f)
        dates = [e["date"] for e in data["entries"]]
        self.assertEqual(dates, sorted(dates))

class TestArchiveEnvelopeShape(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.store_path)
        self.store.load()

    def test_archive_schema_uses_archive_kind(self):
        self.store.add_transaction(date(2020, 1, 1), "old", -100, "other")
        result = purge(self.store, 1, date(2026, 6, 20))
        with open(result.archive_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["schema"], "ledgerlite.archive/3")

    def test_archive_entry_amount_is_signed_decimal_string(self):
        self.store.add_transaction(date(2020, 1, 1), "old", -100, "other")
        result = purge(self.store, 1, date(2026, 6, 20))
        with open(result.archive_path, encoding="utf-8") as f:
            data = json.load(f)
        amount = data["entries"][0]["amount"]
        self.assertIsInstance(amount, str)
        self.assertEqual(amount, "-1.00")

    def test_archive_keys_sorted_alphabetically(self):
        self.store.add_transaction(date(2020, 1, 1), "old", -100, "other")
        result = purge(self.store, 1, date(2026, 6, 20))
        with open(result.archive_path, "rb") as f:
            raw = f.read().decode("utf-8")
        # find positions of the entry object's keys in raw text
        idx_amount = raw.index('"amount"')
        idx_category = raw.index('"category"')
        idx_date = raw.index('"date"')
        idx_description = raw.index('"description"')
        idx_id = raw.index('"id"')
        self.assertTrue(idx_amount < idx_category < idx_date < idx_description < idx_id)


if __name__ == "__main__":
    unittest.main()
