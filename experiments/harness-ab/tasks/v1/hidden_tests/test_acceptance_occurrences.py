import unittest
from datetime import date

from ledgerlite.recurring import RecurringRule, occurrences


def rule(frequency, start, end=None, amount_cents=-1000, category="rent"):
    return RecurringRule(
        id="r1",
        description="test",
        amount_cents=amount_cents,
        category=category,
        frequency=frequency,
        start=start,
        end=end,
    )


class TestWeekly(unittest.TestCase):
    def test_weekly_within_window(self):
        r = rule("weekly", date(2026, 1, 1))
        dates = occurrences(r, date(2026, 1, 1), date(2026, 1, 31))
        self.assertEqual(dates, [date(2026, 1, 1), date(2026, 1, 8), date(2026, 1, 15), date(2026, 1, 22), date(2026, 1, 29)])

    def test_weekly_window_start_after_rule_start(self):
        r = rule("weekly", date(2026, 1, 1))
        dates = occurrences(r, date(2026, 1, 10), date(2026, 1, 20))
        self.assertEqual(dates, [date(2026, 1, 15)])

    def test_weekly_window_exclusive_before_start(self):
        r = rule("weekly", date(2026, 1, 15))
        dates = occurrences(r, date(2026, 1, 1), date(2026, 1, 14))
        self.assertEqual(dates, [])


class TestBiweekly(unittest.TestCase):
    def test_biweekly_within_window(self):
        r = rule("biweekly", date(2026, 1, 1))
        dates = occurrences(r, date(2026, 1, 1), date(2026, 2, 28))
        expected = [date(2026, 1, 1), date(2026, 1, 15), date(2026, 1, 29), date(2026, 2, 12), date(2026, 2, 26)]
        self.assertEqual(dates, expected)


class TestMonthly(unittest.TestCase):
    def test_monthly_basic(self):
        r = rule("monthly", date(2026, 1, 5))
        dates = occurrences(r, date(2026, 1, 1), date(2026, 4, 30))
        self.assertEqual(dates, [date(2026, 1, 5), date(2026, 2, 5), date(2026, 3, 5), date(2026, 4, 5)])

    def test_monthly_clamps_short_month(self):
        r = rule("monthly", date(2026, 1, 31))
        dates = occurrences(r, date(2026, 1, 1), date(2026, 4, 30))
        # 2026 is not a leap year: Feb has 28 days
        self.assertEqual(dates, [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)])

    def test_monthly_clamp_leap_year_february(self):
        r = rule("monthly", date(2024, 1, 31))
        dates = occurrences(r, date(2024, 1, 1), date(2024, 3, 31))
        self.assertEqual(dates, [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31)])

    def test_monthly_clamp_does_not_drift_anchor(self):
        # anchor day 31 clamps in Feb but resumes at 31 in March (not carried from 28)
        r = rule("monthly", date(2026, 1, 31))
        dates = occurrences(r, date(2026, 2, 1), date(2026, 3, 31))
        self.assertEqual(dates, [date(2026, 2, 28), date(2026, 3, 31)])

    def test_monthly_window_inclusive_bounds(self):
        r = rule("monthly", date(2026, 1, 5))
        dates = occurrences(r, date(2026, 1, 5), date(2026, 1, 5))
        self.assertEqual(dates, [date(2026, 1, 5)])


class TestEndDate(unittest.TestCase):
    def test_end_date_limits_occurrences(self):
        r = rule("weekly", date(2026, 1, 1), end=date(2026, 1, 15))
        dates = occurrences(r, date(2026, 1, 1), date(2026, 2, 1))
        self.assertEqual(dates, [date(2026, 1, 1), date(2026, 1, 8), date(2026, 1, 15)])

    def test_end_date_inclusive(self):
        r = rule("weekly", date(2026, 1, 1), end=date(2026, 1, 8))
        dates = occurrences(r, date(2026, 1, 1), date(2026, 2, 1))
        self.assertEqual(dates, [date(2026, 1, 1), date(2026, 1, 8)])


if __name__ == "__main__":
    unittest.main()
