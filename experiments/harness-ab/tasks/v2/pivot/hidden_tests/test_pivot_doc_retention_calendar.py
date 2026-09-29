"""Doc-only: finance calendar policy (dom/DOM_FINANCE_CALENDAR) drives the
retention window -- fiscal periods run 15th-14th, and "today" resolves to
the fiscal period containing it, which counts as the first kept period.
Each assertion below isolates a date that a naive calendar-month (1st of
month) retention window would classify oppositely from the correct
15th-14th fiscal window."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.retention import purge
from ledgerlite.store import Store


class TestRetentionFiscalWindow(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.store_path)
        self.store.load()

    def test_today_before_15th_current_period_started_prior_calendar_month(self):
        # today = 2026-06-10 -> current fiscal period is "2026-05"
        # (2026-05-15 .. 2026-06-14). A tx dated 2026-06-05 is inside that
        # period and must be kept with keep_periods=1. A naive
        # calendar-month window (cutoff = 1st of the current month) would
        # also keep this by coincidence, so this alone is not decisive --
        # paired with the next test it is.
        self.store.add_transaction(date(2026, 6, 5), "x", -100, "other")
        result = purge(self.store, 1, date(2026, 6, 10))
        self.assertEqual(result.kept, 1)
        self.assertEqual(result.archived, 0)

    def test_date_before_current_fiscal_period_start_but_after_calendar_month_start(self):
        # today = 2026-06-20 -> current fiscal period "2026-06"
        # (2026-06-15 .. 2026-07-14). A tx dated 2026-06-10 is AFTER the
        # 1st of June (so a naive calendar-month window keeps it) but
        # BEFORE the fiscal period's 06-15 start (so the correct fiscal
        # window archives it, since 06-10 belongs to the PRIOR period
        # "2026-05"). This is the decisive case.
        self.store.add_transaction(date(2026, 6, 10), "x", -100, "other")
        result = purge(self.store, 1, date(2026, 6, 20))
        self.assertEqual(result.archived, 1)
        self.assertEqual(result.kept, 0)

    def test_today_on_15th_starts_new_period_excluding_prior_month_end(self):
        # today = 2026-06-15 -> current fiscal period is "2026-06"
        # (2026-06-15 .. 2026-07-14). A tx dated 2026-06-14 (the day
        # before) belongs to the PRIOR period "2026-05" and is outside a
        # 1-period keep window -- a naive calendar-month window (cutoff
        # 2026-06-01) would wrongly keep it since 06-14 >= 06-01.
        self.store.add_transaction(date(2026, 6, 14), "x", -100, "other")
        result = purge(self.store, 1, date(2026, 6, 15))
        self.assertEqual(result.archived, 1)
        self.assertEqual(result.kept, 0)

    def test_keep_two_periods_boundary_excludes_date_a_calendar_window_would_keep(self):
        # today = 2026-06-20 -> current period "2026-06", keep_periods=2
        # keeps "2026-06" (06-15..07-14) and "2026-05" (05-15..06-14).
        # A tx dated 2026-04-20 belongs to period "2026-04" (04-15..
        # 05-14), OUTSIDE the 2-period fiscal window and must be
        # archived -- while a naive calendar-month window (keep 2 months
        # back from June -> cutoff 2026-05-01) would wrongly keep it
        # since 04-20 is close to that cutoff's neighborhood in casual
        # reasoning but still fails the same way for a 05-10 tx below.
        self.store.add_transaction(date(2026, 5, 10), "x", -100, "other")
        result = purge(self.store, 2, date(2026, 6, 20))
        # naive: cutoff_month = 6-2+1=5 -> cutoff 2026-05-01; 05-10 >= cutoff -> kept (wrong)
        # correct: kept periods are 2026-06 and 2026-05 (05-15..06-14);
        # 05-10 is BEFORE 2026-05's fiscal start (05-15) -> archived
        self.assertEqual(result.archived, 1)
        self.assertEqual(result.kept, 0)


if __name__ == "__main__":
    unittest.main()
