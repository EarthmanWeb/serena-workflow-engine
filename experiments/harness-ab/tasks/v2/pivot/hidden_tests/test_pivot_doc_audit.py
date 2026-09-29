"""Doc-only: audit policy (dom/DOM_AUDIT) -- applies to any write outside
the primary data store. purge writes an external archive file and must
log it: exact field order/content, appended across runs."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.retention import purge
from ledgerlite.store import Store


class TestPurgeAuditLog(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.store_path)
        self.store.load()
        self.audit_path = os.path.join(self.tmpdir, ".ledgerlite-audit.log")
        self._old_now = os.environ.get("LEDGERLITE_NOW")
        os.environ["LEDGERLITE_NOW"] = "2026-06-20T12:00:00Z"

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("LEDGERLITE_NOW", None)
        else:
            os.environ["LEDGERLITE_NOW"] = self._old_now

    def test_purge_writes_audit_line_next_to_store(self):
        self.store.add_transaction(date(2020, 1, 1), "old", -100, "other")
        purge(self.store, 1, date(2026, 6, 20))
        self.assertTrue(os.path.exists(self.audit_path))

    def test_purge_audit_line_timestamp_and_operation_name(self):
        self.store.add_transaction(date(2020, 1, 1), "old", -100, "other")
        purge(self.store, 1, date(2026, 6, 20))
        with open(self.audit_path) as f:
            line = f.read().strip()
        fields = line.split("|")
        self.assertEqual(fields[0], "2026-06-20T12:00:00Z")
        self.assertEqual(fields[1], "purge")

    def test_purge_audit_line_detail_field_is_archived_count(self):
        self.store.add_transaction(date(2020, 1, 1), "old1", -100, "other")
        self.store.add_transaction(date(2020, 1, 2), "old2", -200, "other")
        purge(self.store, 1, date(2026, 6, 20))
        with open(self.audit_path) as f:
            line = f.read().strip()
        fields = line.split("|")
        self.assertEqual(fields[2], "2")

    def test_purge_audit_log_appends_across_multiple_runs(self):
        self.store.add_transaction(date(2020, 1, 1), "old1", -100, "other")
        purge(self.store, 1, date(2026, 6, 20))

        store2 = Store(self.store_path)
        store2.load()
        store2.add_transaction(date(2019, 1, 1), "old2", -100, "other")
        purge(store2, 1, date(2026, 6, 20))

        with open(self.audit_path) as f:
            lines = [l for l in f.read().splitlines() if l]
        self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main()
