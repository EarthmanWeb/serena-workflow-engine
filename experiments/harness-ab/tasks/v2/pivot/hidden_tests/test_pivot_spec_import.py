"""Spec-level tests for ledgerlite.importer.import_bank_csv: fully
determined by prompt.md's stated signature and row rules -- no doc-only
convention required to pass these. prompt.md does not state the bank
CSV's byte-level date/amount format (that is doc-only, reusing this
project's existing data interchange standard -- see
test_pivot_doc_import_csv_format.py), so these tests only exercise
behaviors true under ANY row format: malformed input is rejected not
raised, row numbering/ordering, wrong field count, unknown category, a
missing source file, and the result's shape."""

import os
import tempfile
import unittest

from ledgerlite.errors import LedgerError
from ledgerlite.importer import ImportResult, import_bank_csv
from ledgerlite.store import Store

_HEADER = "date;description;category;amount"


def _write_csv(path, data_lines):
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write(_HEADER + "\r\n")
        for line in data_lines:
            f.write(line + "\r\n")


class TestImportSpec(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.store_path)
        self.store.load()
        self.csv_path = os.path.join(self.tmpdir, "bank.csv")

    def test_returns_import_result_with_expected_fields(self):
        _write_csv(self.csv_path, ["not-a-date;x;dining;not-a-number"])
        result = import_bank_csv(self.store, self.csv_path)
        self.assertIsInstance(result, ImportResult)
        self.assertTrue(hasattr(result, "added"))
        self.assertTrue(hasattr(result, "skipped_duplicates"))
        self.assertTrue(hasattr(result, "rejected"))

    def test_unparseable_date_rejected_not_raised(self):
        _write_csv(self.csv_path, ["not-a-date;x;dining;5.00"])
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(result.rejected, [1])
        self.assertEqual(result.added, [])

    def test_unparseable_amount_rejected(self):
        _write_csv(self.csv_path, ["not-a-date-either;x;dining;not-a-number"])
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(result.rejected, [1])

    def test_unknown_category_rejected(self):
        # An entirely bogus category is rejected regardless of date/amount
        # format, since it can never resolve to an allowed category.
        _write_csv(self.csv_path, ["not-a-date;x;definitely-not-a-real-category;5.00"])
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(result.rejected, [1])

    def test_wrong_field_count_rejected(self):
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            f.write(_HEADER + "\r\n")
            f.write("only;three;fields\r\n")
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(result.rejected, [1])

    def test_rejected_row_numbers_are_1_based_and_ascending(self):
        _write_csv(
            self.csv_path,
            [
                "bad-1;x;bogus-category-a;5.00",
                "bad-2;x;bogus-category-b;5.00",
                "bad-3;x;bogus-category-c;5.00",
            ],
        )
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(result.rejected, [1, 2, 3])

    def test_header_row_not_counted_as_a_data_row(self):
        _write_csv(self.csv_path, ["bad;x;bogus;5.00"])
        result = import_bank_csv(self.store, self.csv_path)
        # If the header were mis-treated as row 0 data, or counted, the
        # single malformed data row would not land on row number 1.
        self.assertEqual(result.rejected, [1])

    def test_import_does_not_raise_for_row_content_errors(self):
        _write_csv(
            self.csv_path,
            [
                "bad;x;dining;bad-amount",
                "also-bad;x;also-bogus;also-bad-amount",
            ],
        )
        try:
            result = import_bank_csv(self.store, self.csv_path)
        except LedgerError:
            self.fail("import_bank_csv raised for row-content errors")
        self.assertEqual(len(result.rejected), 2)

    def test_missing_file_raises(self):
        with self.assertRaises(Exception):
            import_bank_csv(self.store, os.path.join(self.tmpdir, "nonexistent.csv"))


if __name__ == "__main__":
    unittest.main()
