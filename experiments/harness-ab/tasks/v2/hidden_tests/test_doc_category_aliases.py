"""Doc-only: input normalization policy (dom/DOM_INPUT_NORMALIZATION).
food->groceries, car->transport, fuel->transport accepted wherever a
category is taken as input; exports always show canonical."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.export import export_json
from ledgerlite.store import Store


class TestCategoryAliasesAcceptedOnInput(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()

    def test_food_alias_accepted_and_canonicalized(self):
        tx = self.store.add_transaction(date(2026, 1, 5), "x", -100, "food")
        self.assertEqual(tx.category, "groceries")

    def test_car_alias_accepted_and_canonicalized(self):
        tx = self.store.add_transaction(date(2026, 1, 5), "x", -100, "car")
        self.assertEqual(tx.category, "transport")

    def test_fuel_alias_accepted_and_canonicalized(self):
        tx = self.store.add_transaction(date(2026, 1, 5), "x", -100, "fuel")
        self.assertEqual(tx.category, "transport")

    def test_split_share_accepts_alias(self):
        children = self.store.add_split(date(2026, 1, 5), "x", -100, {"food": 1})
        self.assertEqual(children[0].category, "groceries")


class TestCategoryAliasesCanonicalInExports(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()
        self.store.add_transaction(date(2026, 1, 20), "x", -500, "car")

    def test_export_shows_canonical_category(self):
        import json

        out = os.path.join(self.tmpdir, "out.json")
        export_json(self.store, "2026-01", out)
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["entries"][0]["category"], "transport")


if __name__ == "__main__":
    unittest.main()
