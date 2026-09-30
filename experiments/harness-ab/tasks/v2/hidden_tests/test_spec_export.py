"""Spec-level tests for export_csv / export_json: existence, that files get
written, that they contain the transaction data -- format details are
doc-only and NOT tested here."""

import json
import os
import tempfile
import unittest
from datetime import date

from ledgerlite.export import export_csv, export_json
from ledgerlite.store import Store


class TestExportSpec(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()
        self.store.add_transaction(date(2026, 1, 20), "test-tx", -500, "other")

    def test_export_csv_creates_file(self):
        out = os.path.join(self.tmpdir, "out.csv")
        export_csv(self.store, "2026-01", out)
        self.assertTrue(os.path.exists(out))

    def test_export_csv_file_nonempty(self):
        out = os.path.join(self.tmpdir, "out.csv")
        export_csv(self.store, "2026-01", out)
        self.assertGreater(os.path.getsize(out), 0)

    def test_export_json_creates_file(self):
        out = os.path.join(self.tmpdir, "out.json")
        export_json(self.store, "2026-01", out)
        self.assertTrue(os.path.exists(out))

    def test_export_json_is_valid_json(self):
        out = os.path.join(self.tmpdir, "out.json")
        export_json(self.store, "2026-01", out)
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)

    def test_export_json_contains_entries_list(self):
        out = os.path.join(self.tmpdir, "out.json")
        export_json(self.store, "2026-01", out)
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("entries", data)
        self.assertEqual(len(data["entries"]), 1)


if __name__ == "__main__":
    unittest.main()
