"""Spec-level tests for ledgerlite.split.allocate: fully determined by
task.md's stated signature and the general notion of "integer weights
allocate a total" -- no doc-only convention required to pass these."""

import unittest

from ledgerlite.split import allocate


class TestAllocateSpec(unittest.TestCase):
    def test_returns_dict_keyed_by_category(self):
        result = allocate(1000, {"a": 1, "b": 1})
        self.assertEqual(set(result.keys()), {"a", "b"})

    def test_allocation_sums_to_total_positive(self):
        result = allocate(1000, {"a": 1, "b": 1, "c": 1})
        self.assertEqual(sum(result.values()), 1000)

    def test_allocation_sums_to_total_negative(self):
        result = allocate(-1000, {"a": 1, "b": 1, "c": 1})
        self.assertEqual(sum(result.values()), -1000)

    def test_even_split_two_ways(self):
        result = allocate(1000, {"a": 1, "b": 1})
        self.assertEqual(result["a"] + result["b"], 1000)
        self.assertEqual(min(result.values()), 500)
        self.assertEqual(max(result.values()), 500)

    def test_weighted_split_proportional(self):
        result = allocate(3000, {"a": 2, "b": 1})
        # a should get roughly twice b
        self.assertGreater(result["a"], result["b"])

    def test_single_category_gets_everything(self):
        result = allocate(1234, {"only": 1})
        self.assertEqual(result["only"], 1234)

    def test_zero_weight_raises_ledger_error(self):
        from ledgerlite.errors import LedgerError

        with self.assertRaises(LedgerError):
            allocate(1000, {"a": 0, "b": 1})

    def test_negative_weight_raises_ledger_error(self):
        from ledgerlite.errors import LedgerError

        with self.assertRaises(LedgerError):
            allocate(1000, {"a": -1, "b": 1})


if __name__ == "__main__":
    unittest.main()
