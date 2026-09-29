"""Doc-only: input normalization policy (dom/DOM_INPUT_NORMALIZATION)
applies to imported categories too -- food->groceries, car->transport,
fuel->transport; canonical name stored."""

import os
import tempfile
import unittest

from ledgerlite.importer import import_bank_csv
from ledgerlite.store import Store

_HEADER = "date;description;category;amount"


def _write_csv(path, data_lines):
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write(_HEADER + "\r\n")
        for line in data_lines:
            f.write(line + "\r\n")


class TestImportCategoryAliases(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.store_path)
        self.store.load()
        self.csv_path = os.path.join(self.tmpdir, "bank.csv")

    def test_food_alias_canonicalized_on_import(self):
        _write_csv(self.csv_path, ["05.01.2026;x;food;-4,50"])
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(result.added[0].category, "groceries")

    def test_car_alias_canonicalized_on_import(self):
        _write_csv(self.csv_path, ["05.01.2026;x;car;-40,00"])
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(result.added[0].category, "transport")

    def test_fuel_alias_canonicalized_on_import(self):
        _write_csv(self.csv_path, ["05.01.2026;x;fuel;-40,00"])
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(result.added[0].category, "transport")


if __name__ == "__main__":
    unittest.main()
