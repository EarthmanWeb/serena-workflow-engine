"""Doc-only: data interchange standard (ref/REF_DATA_INTERCHANGE) applies
to the imported bank CSV too -- semicolon delimiter, DD.MM.YYYY dates,
comma-decimal signed amounts, BOM tolerated, CRLF."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.importer import import_bank_csv
from ledgerlite.store import Store


class TestImportCsvFormat(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.store_path)
        self.store.load()
        self.csv_path = os.path.join(self.tmpdir, "bank.csv")

    def _write_bytes(self, text_body, bom=True):
        with open(self.csv_path, "wb") as f:
            if bom:
                f.write(b"\xef\xbb\xbf")
            f.write(text_body.encode("utf-8"))

    def test_semicolon_delimiter_accepted(self):
        body = "date;description;category;amount\r\n20.01.2026;coffee;dining;-4,50\r\n"
        self._write_bytes(body)
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(len(result.added), 1)

    def test_ddmmyyyy_date_parsed_correctly(self):
        body = "date;description;category;amount\r\n20.01.2026;coffee;dining;-4,50\r\n"
        self._write_bytes(body)
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(result.added[0].date, date(2026, 1, 20))

    def test_comma_decimal_negative_amount_parsed(self):
        body = "date;description;category;amount\r\n20.01.2026;coffee;dining;-4,50\r\n"
        self._write_bytes(body)
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(result.added[0].amount_cents, -450)

    def test_bom_tolerated(self):
        body = "date;description;category;amount\r\n20.01.2026;coffee;dining;-4,50\r\n"
        self._write_bytes(body, bom=True)
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(len(result.added), 1)
        self.assertEqual(len(result.rejected), 0)

    def test_crlf_rows_accepted(self):
        body = (
            "date;description;category;amount\r\n"
            "20.01.2026;a;dining;-1,00\r\n"
            "21.01.2026;b;dining;-2,00\r\n"
        )
        self._write_bytes(body)
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(len(result.added), 2)


if __name__ == "__main__":
    unittest.main()
