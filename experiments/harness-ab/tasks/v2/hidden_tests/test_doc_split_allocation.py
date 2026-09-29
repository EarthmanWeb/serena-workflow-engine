"""Doc-only: split allocation rules (dom/DOM_SPLIT_ALLOCATION).
Largest-remainder method; leftover cents to largest weight, ties broken
alphabetically; child descriptions "<desc> [split i/n]"."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.split import allocate
from ledgerlite.store import Store


class TestSplitAllocationDoc(unittest.TestCase):
    def test_largest_remainder_gets_leftover_cent(self):
        # 1000 cents / weights 2:1:1 -> raw 500:250:250, exact, no remainder
        # use a case with a genuine remainder instead: 100 cents, weights 1:1:1
        result = allocate(100, {"a": 1, "b": 1, "c": 1})
        # 33,33,33 = 99, one leftover cent goes to alphabetically-first tie
        self.assertEqual(result["a"], 34)
        self.assertEqual(result["b"], 33)
        self.assertEqual(result["c"], 33)

    def test_tie_broken_alphabetically_not_by_dict_order(self):
        result = allocate(100, {"zebra": 1, "apple": 1, "mango": 1})
        self.assertEqual(result["apple"], 34)
        self.assertEqual(result["zebra"], 33)
        self.assertEqual(result["mango"], 33)

    def test_larger_weight_favored_for_remainder_when_not_tied(self):
        # total 10, weights a=3,b=2 -> raw a=6.0 b=4.0 exact; use uneven total
        result = allocate(11, {"a": 3, "b": 2})
        # raw: a = 33/5=6.6 -> 6 r 3; b = 22/5=4.4 -> 4 r 2; leftover=1 -> a (larger remainder)
        self.assertEqual(result["a"], 7)
        self.assertEqual(result["b"], 4)

    def test_negative_total_preserves_sign_per_category(self):
        result = allocate(-100, {"a": 1, "b": 1, "c": 1})
        self.assertTrue(all(v <= 0 for v in result.values()))
        self.assertEqual(sum(result.values()), -100)

    def test_negative_total_largest_remainder_still_alphabetical(self):
        result = allocate(-100, {"zebra": 1, "apple": 1, "mango": 1})
        self.assertEqual(result["apple"], -34)


class TestSplitChildDescriptionDoc(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()

    def test_child_description_format(self):
        children = self.store.add_split(date(2026, 1, 5), "Dinner", -3000, {"dining": 1, "groceries": 1})
        descriptions = {c.description for c in children}
        self.assertIn("Dinner [split 1/2]", descriptions)
        self.assertIn("Dinner [split 2/2]", descriptions)

    def test_child_description_index_follows_alphabetical_category_order(self):
        # groceries < transport alphabetically -> groceries is split 1/2
        children = self.store.add_split(date(2026, 1, 5), "Trip", -1000, {"transport": 1, "groceries": 1})
        by_category = {c.category: c.description for c in children}
        self.assertEqual(by_category["groceries"], "Trip [split 1/2]")
        self.assertEqual(by_category["transport"], "Trip [split 2/2]")

    def test_three_way_split_description_indices(self):
        children = self.store.add_split(
            date(2026, 1, 5), "Big trip", -3000, {"transport": 1, "dining": 1, "groceries": 1}
        )
        by_category = {c.category: c.description for c in children}
        self.assertEqual(by_category["dining"], "Big trip [split 1/3]")
        self.assertEqual(by_category["groceries"], "Big trip [split 2/3]")
        self.assertEqual(by_category["transport"], "Big trip [split 3/3]")


if __name__ == "__main__":
    unittest.main()
