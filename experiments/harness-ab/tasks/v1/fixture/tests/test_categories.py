import unittest

from ledgerlite.categories import ALLOWED_CATEGORIES


class TestCategories(unittest.TestCase):
    def test_allowed_categories_fixed_set(self):
        self.assertEqual(
            ALLOWED_CATEGORIES,
            {"groceries", "rent", "utilities", "transport", "dining", "salary", "other"},
        )


if __name__ == "__main__":
    unittest.main()
