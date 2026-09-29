"""Doc-only: privacy redaction in exports only (dom/DOM_PRIVACY_REDACTION).
Descriptions with a 12-19 digit run -> "****" + last 4 digits. Case-
insensitive "ssn" followed by digits -> "SSN:REDACTED". Redaction applies
ONLY to exports, never to the CLI `list`/`statement` output or the raw
store."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.export import export_csv, export_json, redact
from ledgerlite.statement import build_statement, render_statement
from ledgerlite.store import Store


class TestRedactFunction(unittest.TestCase):
    def test_redacts_16_digit_number(self):
        result = redact("card 1234567890123456 charged")
        self.assertIn("****3456", result)
        self.assertNotIn("1234567890123456", result)

    def test_redacts_12_digit_number_minimum(self):
        result = redact("id 123456789012 here")
        self.assertIn("****9012", result)

    def test_does_not_redact_11_digit_number(self):
        result = redact("id 12345678901 here")
        self.assertEqual(result, "id 12345678901 here")

    def test_redacts_ssn_case_insensitive(self):
        self.assertIn("SSN:REDACTED", redact("SSN: 123456789"))
        self.assertIn("SSN:REDACTED", redact("ssn 123456789"))
        self.assertIn("SSN:REDACTED", redact("Ssn#123456789"))

    def test_unaffected_text_unchanged(self):
        self.assertEqual(redact("groceries run"), "groceries run")


class TestRedactionAppliesOnlyToExports(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()
        self.store.add_transaction(date(2026, 1, 20), "card 1234567890123456", -500, "other")

    def test_store_transaction_description_unredacted(self):
        tx = self.store.transactions[0]
        self.assertEqual(tx.description, "card 1234567890123456")

    def test_statement_render_unredacted(self):
        stmt = build_statement(self.store, "2026-01")
        rendered = render_statement(stmt)
        self.assertIn("1234567890123456", rendered)

    def test_csv_export_redacted(self):
        out = os.path.join(self.tmpdir, "out.csv")
        export_csv(self.store, "2026-01", out)
        with open(out, "rb") as f:
            text = f.read().decode("utf-8-sig")
        self.assertNotIn("1234567890123456", text)
        self.assertIn("****3456", text)

    def test_json_export_redacted(self):
        out = os.path.join(self.tmpdir, "out.json")
        export_json(self.store, "2026-01", out)
        with open(out, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("1234567890123456", text)
        self.assertIn("****3456", text)


if __name__ == "__main__":
    unittest.main()
