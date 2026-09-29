"""Doc-only: external file format standard (ref/REF_DATA_INTERCHANGE).
CSV: semicolon delimiter, exact header, DD.MM.YYYY dates, comma-decimal
amounts with trailing "-" for negative and no sign for non-negative,
UTF-8 BOM, CRLF line endings. JSON: envelope
{"schema": "ledgerlite.export/3", ...} with sorted keys, amounts as
decimal strings. Column order and exact envelope shape from task.md;
byte-level formatting rules from the memory."""

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
        self.assertEqual(raw[:3], b"\xef\xbb\xbf")

    def test_csv_uses_crlf_line_endings_exactly(self):
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "other")
        export_csv(self.store, "2026-01", self.out)
        with open(self.out, "rb") as f:
            raw = f.read()
        body = raw[3:]  # strip BOM
        # Every line ends CRLF and there are no bare LFs.
        self.assertEqual(body.count(b"\n"), body.count(b"\r\n"))
        self.assertGreaterEqual(body.count(b"\r\n"), 2)  # header + 1 data row

    def test_csv_header_exact(self):
        export_csv(self.store, "2026-01", self.out)
        with open(self.out, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8-sig")
        first_line = text.split("\r\n")[0]
        self.assertEqual(first_line, "id;date;description;category;amount")

    def test_csv_data_row_exact(self):
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "other")
        export_csv(self.store, "2026-01", self.out)
        with open(self.out, "rb") as f:
            text = f.read().decode("utf-8-sig")
        data_line = text.split("\r\n")[1]
        self.assertEqual(data_line, "t1;20.01.2026;x;other;-5,00")

    def test_csv_amount_comma_decimal_income_no_sign_exact(self):
        self.store.add_transaction(date(2026, 1, 20), "pay", 500, "salary")
        export_csv(self.store, "2026-01", self.out)
        with open(self.out, "rb") as f:
            text = f.read().decode("utf-8-sig")
        data_line = text.split("\r\n")[1]
        self.assertEqual(data_line, "t1;20.01.2026;pay;salary;5,00")


class TestJsonExportFormat(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()
        self.out = os.path.join(self.tmpdir, "out.json")

    def test_json_schema_field_exact(self):
        export_json(self.store, "2026-01", self.out)
        with open(self.out, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["schema"], "ledgerlite.export/3")

    def test_json_period_envelope_exact(self):
        export_json(self.store, "2026-01", self.out)
        with open(self.out, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["period"], {"start": "2026-01-15", "end": "2026-02-14"})

    def test_json_entry_exact(self):
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "other")
        export_json(self.store, "2026-01", self.out)
        with open(self.out, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(
            data["entries"][0],
            {
                "id": "t1",
                "date": "2026-01-20",
                "description": "x",
                "category": "other",
                "amount": "-5.00",
            },
        )
        self.assertIsInstance(data["entries"][0]["amount"], str)

    def test_json_keys_sorted_exact_order(self):
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "other")
        export_json(self.store, "2026-01", self.out)
        with open(self.out, encoding="utf-8") as f:
            raw_text = f.read()
        entry_block = raw_text[raw_text.index("{", raw_text.index('"entries"')):]
        key_positions = {
            key: entry_block.index(f'"{key}"')
            for key in ("amount", "category", "date", "description", "id")
        }
        self.assertEqual(
            sorted(key_positions, key=key_positions.get),
            ["amount", "category", "date", "description", "id"],
        )


if __name__ == "__main__":
    unittest.main()
