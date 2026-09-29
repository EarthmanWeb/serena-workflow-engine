"""Doc-only: error code naming scheme (ref/REF_ERROR_HANDLING) applied to
the four conditions task.md lists in section 5, deriving
E_FISCAL_PERIOD, E_EXPORT_FORMAT, E_SPLIT_WEIGHTS, E_EXPORT_EXISTS."""

import os
import tempfile
import unittest
from datetime import date

from ledgerlite.errors import (
    E_EXPORT_EXISTS,
    E_EXPORT_FORMAT,
    E_FISCAL_PERIOD,
    E_SPLIT_WEIGHTS,
    LedgerError,
)
from ledgerlite.export import export, export_csv
from ledgerlite.statement import fiscal_period_bounds
from ledgerlite.split import allocate
from ledgerlite.store import Store


class TestErrorCodesExist(unittest.TestCase):
    def test_error_code_constants_defined(self):
        self.assertEqual(E_FISCAL_PERIOD, "E_FISCAL_PERIOD")
        self.assertEqual(E_EXPORT_FORMAT, "E_EXPORT_FORMAT")
        self.assertEqual(E_SPLIT_WEIGHTS, "E_SPLIT_WEIGHTS")
        self.assertEqual(E_EXPORT_EXISTS, "E_EXPORT_EXISTS")


class TestFiscalPeriodError(unittest.TestCase):
    def test_bad_period_format_raises(self):
        with self.assertRaises(LedgerError) as cm:
            fiscal_period_bounds("2026/01")
        self.assertEqual(cm.exception.code, E_FISCAL_PERIOD)

    def test_bad_period_month_out_of_range_raises(self):
        with self.assertRaises(LedgerError) as cm:
            fiscal_period_bounds("2026-13")
        self.assertEqual(cm.exception.code, E_FISCAL_PERIOD)


class TestExportFormatError(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()

    def test_unknown_format_raises(self):
        out = os.path.join(self.tmpdir, "out.xyz")
        with self.assertRaises(LedgerError) as cm:
            export(self.store, "xml", "2026-01", out)
        self.assertEqual(cm.exception.code, E_EXPORT_FORMAT)


class TestSplitWeightsError(unittest.TestCase):
    def test_negative_weight_raises(self):
        with self.assertRaises(LedgerError) as cm:
            allocate(1000, {"a": -1})
        self.assertEqual(cm.exception.code, E_SPLIT_WEIGHTS)


class TestExportExistsError(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.path)
        self.store.load()
        self.out = os.path.join(self.tmpdir, "out.csv")

    def test_refuses_overwrite_without_force(self):
        export_csv(self.store, "2026-01", self.out)
        with self.assertRaises(LedgerError) as cm:
            export_csv(self.store, "2026-01", self.out)
        self.assertEqual(cm.exception.code, E_EXPORT_EXISTS)

    def test_force_allows_overwrite(self):
        export_csv(self.store, "2026-01", self.out)
        export_csv(self.store, "2026-01", self.out, force=True)  # should not raise


if __name__ == "__main__":
    unittest.main()
