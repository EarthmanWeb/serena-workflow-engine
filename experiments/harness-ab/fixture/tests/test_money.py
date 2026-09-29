import unittest

from ledgerlite.errors import E_INVALID_AMOUNT, LedgerError
from ledgerlite.money import format_cents, parse_amount


class TestParseAmount(unittest.TestCase):
    def test_parses_positive_decimal(self):
        self.assertEqual(parse_amount("12.34"), 1234)

    def test_parses_negative_integer(self):
        self.assertEqual(parse_amount("-5"), -500)

    def test_parses_fractional(self):
        self.assertEqual(parse_amount("0.5"), 50)

    def test_parses_zero(self):
        self.assertEqual(parse_amount("0"), 0)

    def test_invalid_text_raises(self):
        with self.assertRaises(LedgerError) as cm:
            parse_amount("abc")
        self.assertEqual(cm.exception.code, E_INVALID_AMOUNT)

    def test_too_many_decimal_places_raises(self):
        with self.assertRaises(LedgerError):
            parse_amount("1.234")

    def test_empty_string_raises(self):
        with self.assertRaises(LedgerError):
            parse_amount("")


class TestFormatCents(unittest.TestCase):
    def test_formats_positive(self):
        self.assertEqual(format_cents(1234), "12.34")

    def test_formats_negative(self):
        self.assertEqual(format_cents(-500), "-5.00")

    def test_formats_zero(self):
        self.assertEqual(format_cents(0), "0.00")

    def test_formats_small_fraction(self):
        self.assertEqual(format_cents(5), "0.05")


if __name__ == "__main__":
    unittest.main()
