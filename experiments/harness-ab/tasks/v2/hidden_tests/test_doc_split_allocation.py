"""Doc-only: money distribution policy (dom/DOM_MONEY_DISTRIBUTION).
Largest-remainder method; leftover cents to largest remainder, ties
broken alphabetically; derived labels "<original> [<i>/<n>]"."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.split import allocate
from ledgerlite.store import Store


class TestSplitAllocationDoc(unittest.TestCase):
    def test_largest_remainder_gets_leftover_cent_exact(self):
        # 100 cents / weights 1:1:1 -> raw 33.33 each; one leftover cent
        # goes to the alphabetically-first tied category.
        result = allocate(100, {"a": 1, "b": 1, "c": 1})
        self.assertEqual(result, {"a": 34, "b": 33, "c": 33})

    def test_tie_broken_alphabetically_not_by_dict_order_exact(self):
        result = allocate(100, {"zebra": 1, "apple": 1, "mango": 1})
        self.assertEqual(result, {"zebra": 33, "apple": 34, "mango": 33})

    def test_larger_remainder_favored_when_not_tied_exact(self):
        # total 11, weights a=3,b=2 -> raw a=6.6 (r 0.6), b=4.4 (r 0.4);
        # leftover=1 cent goes to a (larger remainder, no tie).
        result = allocate(11, {"a": 3, "b": 2})
        self.assertEqual(result, {"a": 7, "b": 4})

    def test_negative_total_preserves_sign_and_sum_exact(self):
        result = allocate(-100, {"a": 1, "b": 1, "c": 1})
        self.assertEqual(result, {"a": -34, "b": -33, "c": -33})

    def test_negative_total_largest_remainder_still_alphabetical_exact(self):
        result = allocate(-100, {"zebra": 1, "apple": 1, "mango": 1})
        self.assertEqual(result, {"zebra": -33, "apple": -34, "mango": -33})

    def test_single_category_exact(self):
        result = allocate(1234, {"only": 1})
        self.assertEqual(result, {"only": 1234})


class TestSplitChildDescriptionDoc(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()

    def test_child_description_format_exact(self):
        children = self.store.add_split(date(2026, 1, 5), "Dinner", -3000, {"dining": 1, "groceries": 1})
        by_category = {c.category: c.description for c in children}
        # dining < groceries alphabetically -> dining is 1/2
        self.assertEqual(by_category["dining"], "Dinner [1/2]")
        self.assertEqual(by_category["groceries"], "Dinner [2/2]")

    def test_child_description_index_follows_alphabetical_category_order_exact(self):
        # groceries < transport alphabetically -> groceries is 1/2
        children = self.store.add_split(date(2026, 1, 5), "Trip", -1000, {"transport": 1, "groceries": 1})
        by_category = {c.category: c.description for c in children}
        self.assertEqual(by_category["groceries"], "Trip [1/2]")
        self.assertEqual(by_category["transport"], "Trip [2/2]")

    def test_three_way_split_description_indices_exact(self):
        children = self.store.add_split(
            date(2026, 1, 5), "Big trip", -3000, {"transport": 1, "dining": 1, "groceries": 1}
        )
        by_category = {c.category: c.description for c in children}
        self.assertEqual(by_category["dining"], "Big trip [1/3]")
        self.assertEqual(by_category["groceries"], "Big trip [2/3]")
        self.assertEqual(by_category["transport"], "Big trip [3/3]")

    def test_children_returned_in_alphabetical_category_order_exact(self):
        children = self.store.add_split(
            date(2026, 1, 5), "Big trip", -3000, {"transport": 1, "dining": 1, "groceries": 1}
        )
        self.assertEqual([c.category for c in children], ["dining", "groceries", "transport"])


if __name__ == "__main__":
    unittest.main()
