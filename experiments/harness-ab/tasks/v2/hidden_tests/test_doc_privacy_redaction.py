"""Doc-only: privacy policy (dom/DOM_PRIVACY). Descriptions with a 12-19
digit run -> "****" + last 4 digits. Case-insensitive "ssn" followed by
digits -> "SSN:REDACTED". Redaction applies ONLY to exports, never to the
CLI `list`/`statement` output or the raw store."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.export import export_csv, export_json, redact
from ledgerlite.statement import build_statement, render_statement
from ledgerlite.store import Store


class TestRedactFunction(unittest.TestCase):
    def test_redacts_16_digit_number_exact(self):
        result = redact("card 1234567890123456 charged")
        self.assertEqual(result, "card ****3456 charged")

    def test_redacts_12_digit_number_minimum_exact(self):
        result = redact("id 123456789012 here")
        self.assertEqual(result, "id ****9012 here")

    def test_does_not_redact_11_digit_number(self):
        result = redact("id 12345678901 here")
        self.assertEqual(result, "id 12345678901 here")

    def test_does_not_redact_20_digit_number(self):
        result = redact("id 12345678901234567890 here")
        self.assertEqual(result, "id 12345678901234567890 here")

    def test_redacts_ssn_case_insensitive_exact(self):
        self.assertEqual(redact("SSN: 123456789"), "SSN:REDACTED")
        self.assertEqual(redact("ssn 123456789"), "SSN:REDACTED")
        self.assertEqual(redact("Ssn#123456789 on file"), "SSN:REDACTED on file")

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

    def test_csv_export_redacted_exact(self):
        out = os.path.join(self.tmpdir, "out.csv")
        export_csv(self.store, "2026-01", out)
        with open(out, "rb") as f:
            text = f.read().decode("utf-8-sig")
        data_line = text.split("\r\n")[1]
        self.assertEqual(data_line, "t1;20.01.2026;card ****3456;other;-5,00")

    def test_json_export_redacted_exact(self):
        out = os.path.join(self.tmpdir, "out.json")
        export_json(self.store, "2026-01", out)
        import json

        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["entries"][0]["description"], "card ****3456")


if __name__ == "__main__":
    unittest.main()
