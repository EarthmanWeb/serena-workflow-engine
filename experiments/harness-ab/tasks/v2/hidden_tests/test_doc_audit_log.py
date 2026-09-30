"""Doc-only: audit policy (dom/DOM_AUDIT). Every export appends one line to
.ledgerlite-audit.log next to the ledger file:
"<ISO8601 UTC>|export|<format>|<period>|<count>" (operation name "export",
then that operation's own detail fields in task.md's listed order: format,
period, count). Timestamp from env LEDGERLITE_NOW when set."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.export import export_csv, export_json
from ledgerlite.store import Store


class TestAuditLog(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "other")
        self.audit_path = os.path.join(self.tmpdir, ".ledgerlite-audit.log")
        self._old_now = os.environ.get("LEDGERLITE_NOW")
        os.environ["LEDGERLITE_NOW"] = "2026-01-20T12:00:00Z"

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("LEDGERLITE_NOW", None)
        else:
            os.environ["LEDGERLITE_NOW"] = self._old_now

    def test_audit_log_created_next_to_ledger_file(self):
        out = os.path.join(self.tmpdir, "out.csv")
        export_csv(self.store, "2026-01", out)
        self.assertTrue(os.path.exists(self.audit_path))

    def test_audit_log_line_format_csv(self):
        out = os.path.join(self.tmpdir, "out.csv")
        export_csv(self.store, "2026-01", out)
        with open(self.audit_path) as f:
            line = f.read().strip()
        self.assertEqual(line, "2026-01-20T12:00:00Z|export|csv|2026-01|1")

    def test_audit_log_line_format_json(self):
        out = os.path.join(self.tmpdir, "out.json")
        export_json(self.store, "2026-01", out)
        with open(self.audit_path) as f:
            line = f.read().strip()
        self.assertEqual(line, "2026-01-20T12:00:00Z|export|json|2026-01|1")

    def test_audit_log_appends_not_overwrites(self):
        out1 = os.path.join(self.tmpdir, "out.csv")
        out2 = os.path.join(self.tmpdir, "out2.json")
        export_csv(self.store, "2026-01", out1)
        export_json(self.store, "2026-01", out2)
        with open(self.audit_path) as f:
            lines = [l for l in f.read().splitlines() if l]
        self.assertEqual(len(lines), 2)

    def test_audit_log_count_reflects_entry_count_exact(self):
        self.store.add_transaction(date(2026, 1, 21), "y", -200, "other")
        out = os.path.join(self.tmpdir, "out.csv")
        export_csv(self.store, "2026-01", out)
        with open(self.audit_path) as f:
            line = f.read().strip()
        self.assertEqual(line, "2026-01-20T12:00:00Z|export|csv|2026-01|2")


if __name__ == "__main__":
    unittest.main()
