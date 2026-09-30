"""Doc-only: error handling standard (ref/REF_ERROR_HANDLING) scheme
E_<AREA>_<CONDITION> applied to the new retention validation failure --
area word from the module (RETENTION), condition word from prompt.md's
own vocabulary for the failure (PERIODS: "keep_periods must be a
positive integer"). Same LedgerError/CLI contract as every other code."""

import contextlib
import io
import os
import tempfile
import unittest
from datetime import date

from ledgerlite.cli import main
from ledgerlite.errors import E_RETENTION_PERIODS, LedgerError
from ledgerlite.retention import purge
from ledgerlite.store import Store


class TestRetentionErrorCode(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.store_path)
        self.store.load()

    def test_error_code_constant_defined(self):
        self.assertEqual(E_RETENTION_PERIODS, "E_RETENTION_PERIODS")

    def test_zero_keep_periods_raises_with_correct_code(self):
        with self.assertRaises(LedgerError) as ctx:
            purge(self.store, 0, date(2026, 6, 20))
        self.assertEqual(ctx.exception.code, E_RETENTION_PERIODS)

    def test_negative_keep_periods_raises_with_correct_code(self):
        with self.assertRaises(LedgerError) as ctx:
            purge(self.store, -3, date(2026, 6, 20))
        self.assertEqual(ctx.exception.code, E_RETENTION_PERIODS)


class TestRetentionCliErrorContract(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")

    def run_cli(self, args):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--file", self.path] + args)
        return code, out.getvalue(), err.getvalue()

    def test_cli_prints_error_code_and_exits_2(self):
        code, out, err = self.run_cli(["purge", "--keep", "0"])
        self.assertEqual(code, 2)
        self.assertTrue(err.strip().startswith("error: E_RETENTION_PERIODS: "))

    def test_cli_error_goes_to_stderr_not_stdout(self):
        code, out, err = self.run_cli(["purge", "--keep", "0"])
        self.assertEqual(out, "")
        self.assertIn("error: E_RETENTION_PERIODS", err)


if __name__ == "__main__":
    unittest.main()
