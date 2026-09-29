import unittest

from ledgerlite.errors import E_INVALID_AMOUNT, E_NOT_FOUND, E_UNKNOWN_CATEGORY, LedgerError


class TestLedgerError(unittest.TestCase):
    def test_has_code_and_message(self):
        err = LedgerError(E_INVALID_AMOUNT, "bad amount")
        self.assertEqual(err.code, E_INVALID_AMOUNT)
        self.assertEqual(err.message, "bad amount")

    def test_error_codes_are_strings(self):
        for code in (E_INVALID_AMOUNT, E_UNKNOWN_CATEGORY, E_NOT_FOUND):
            self.assertIsInstance(code, str)


if __name__ == "__main__":
    unittest.main()
