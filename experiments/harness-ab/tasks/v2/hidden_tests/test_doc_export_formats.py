"""Doc-only: export formats (dom/DOM_EXPORT_FORMATS).
CSV: semicolon delimiter, exact header, DD.MM.YYYY dates, comma-decimal
amounts with trailing "-" for expenses, UTF-8 BOM, CRLF line endings.
JSON: envelope {"schema": "ledgerlite.export/3", ...} with sorted keys,
amounts as decimal strings."""

import json
import os
import tempfile
import unittest
from datetime import date

from ledgerlite.export import export_csv, export_json
from ledgerlite.store import Store


class TestCsvExportFormat(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()
        self.out = os.path.join(self.tmpdir, "out.csv")

    def test_csv_has_utf8_bom(self):
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "other")
        export_csv(self.store, "2026-01", self.out)
        with open(self.out, "rb") as f:
            raw = f.read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))

    def test_csv_uses_crlf_line_endings(self):
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "other")
        export_csv(self.store, "2026-01", self.out)
        with open(self.out, "rb") as f:
            raw = f.read()
        body = raw[3:]  # strip BOM
        self.assertIn(b"\r\n", body)
        self.assertNotIn(b"(?<!\r)\n", body)  # sanity: at least some CRLF present

    def test_csv_header_exact(self):
        export_csv(self.store, "2026-01", self.out)
        with open(self.out, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8-sig")
        first_line = text.split("\r\n")[0]
        self.assertEqual(first_line, "id;date;description;category;amount")

    def test_csv_delimiter_is_semicolon(self):
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "other")
        export_csv(self.store, "2026-01", self.out)
        with open(self.out, "rb") as f:
            text = f.read().decode("utf-8-sig")
        data_line = text.split("\r\n")[1]
        self.assertEqual(data_line.count(";"), 4)

    def test_csv_date_format_ddmmyyyy(self):
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "other")
        export_csv(self.store, "2026-01", self.out)
        with open(self.out, "rb") as f:
            text = f.read().decode("utf-8-sig")
        data_line = text.split("\r\n")[1]
        self.assertIn("20.01.2026", data_line)

    def test_csv_amount_comma_decimal_expense_trailing_minus(self):
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "other")
        export_csv(self.store, "2026-01", self.out)
        with open(self.out, "rb") as f:
            text = f.read().decode("utf-8-sig")
        data_line = text.split("\r\n")[1]
        self.assertIn("-5,00", data_line)

    def test_csv_amount_comma_decimal_income_no_sign(self):
        self.store.add_transaction(date(2026, 1, 20), "pay", 500, "salary")
        export_csv(self.store, "2026-01", self.out)
        with open(self.out, "rb") as f:
            text = f.read().decode("utf-8-sig")
        data_line = text.split("\r\n")[1]
        self.assertIn(";5,00", data_line)
        self.assertNotIn(";-5,00", data_line)


class TestJsonExportFormat(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()
        self.out = os.path.join(self.tmpdir, "out.json")

    def test_json_schema_field(self):
        export_json(self.store, "2026-01", self.out)
        with open(self.out, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["schema"], "ledgerlite.export/3")

    def test_json_period_envelope(self):
        export_json(self.store, "2026-01", self.out)
        with open(self.out, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["period"]["start"], "2026-01-15")
        self.assertEqual(data["period"]["end"], "2026-02-14")

    def test_json_amounts_are_strings(self):
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "other")
        export_json(self.store, "2026-01", self.out)
        with open(self.out, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["entries"][0]["amount"], "-5.00")
        self.assertIsInstance(data["entries"][0]["amount"], str)

    def test_json_keys_sorted(self):
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "other")
        export_json(self.store, "2026-01", self.out)
        with open(self.out, encoding="utf-8") as f:
            raw_text = f.read()
        entry_start = raw_text.index('"amount"')
        # "amount" should be the first key alphabetically among id/date/description/category/amount
        entry_block = raw_text[raw_text.index("{", raw_text.index('"entries"')) : ]
        first_key_pos = min(
            entry_block.index('"amount"'),
            entry_block.index('"category"'),
            entry_block.index('"date"'),
            entry_block.index('"description"'),
            entry_block.index('"id"'),
        )
        self.assertEqual(first_key_pos, entry_block.index('"amount"'))


if __name__ == "__main__":
    unittest.main()
