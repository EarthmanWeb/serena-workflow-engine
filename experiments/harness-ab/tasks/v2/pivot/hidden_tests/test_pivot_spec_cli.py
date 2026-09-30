"""Spec-level tests for the new `import` and `purge` CLI subcommands:
existence and basic exit codes, as stated in prompt.md."""

import contextlib
import io
import os
import tempfile
import unittest
from datetime import date

from ledgerlite.cli import main
from ledgerlite.store import Store


class TestImportPurgeCliSpec(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        self.bank_csv = os.path.join(self.tmpdir, "bank.csv")
        with open(self.bank_csv, "w", newline="", encoding="utf-8") as f:
            f.write("date;description;category;amount\r\n")
            f.write("05.01.2026;coffee;dining;-4,50\r\n")

    def run_cli(self, args):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--file", self.path] + args)
        return code, out.getvalue(), err.getvalue()

    def test_import_subcommand_exists(self):
        code, out, err = self.run_cli(["import", "--file", self.bank_csv])
        self.assertEqual(code, 0)

    def test_import_prints_summary_line(self):
        code, out, err = self.run_cli(["import", "--file", self.bank_csv])
        self.assertEqual(code, 0)
        self.assertIn("imported", out)

    def test_purge_subcommand_exists(self):
        os.environ["LEDGERLITE_NOW"] = "2026-06-20T00:00:00Z"
        try:
            code, out, err = self.run_cli(["purge", "--keep", "1"])
        finally:
            os.environ.pop("LEDGERLITE_NOW", None)
        self.assertEqual(code, 0)

    def test_purge_with_zero_keep_errors(self):
        code, out, err = self.run_cli(["purge", "--keep", "0"])
        self.assertEqual(code, 2)
        self.assertIn("error:", err)


if __name__ == "__main__":
    unittest.main()
