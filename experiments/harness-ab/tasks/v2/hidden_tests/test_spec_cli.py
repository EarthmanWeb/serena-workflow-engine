"""Spec-level tests for the new CLI subcommands: existence and basic exit
codes, as stated in task.md."""

import contextlib
import io
import os
import tempfile
import unittest

from ledgerlite.cli import main


class TestCliSpec(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")

    def run_cli(self, args):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--file", self.path] + args)
        return code, out.getvalue(), err.getvalue()

    def test_split_subcommand_exists(self):
        code, out, err = self.run_cli(
            ["split", "--date", "2026-01-05", "--description", "Dinner", "--total", "-30.00",
             "--share", "dining=1", "--share", "groceries=1"]
        )
        self.assertEqual(code, 0)

    def test_statement_subcommand_exists(self):
        code, out, err = self.run_cli(["statement", "--period", "2026-01"])
        self.assertEqual(code, 0)

    def test_export_csv_subcommand_exists(self):
        out_path = os.path.join(self.tmpdir, "out.csv")
        code, out, err = self.run_cli(["export", "--format", "csv", "--period", "2026-01", "--out", out_path])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(out_path))

    def test_export_json_subcommand_exists(self):
        out_path = os.path.join(self.tmpdir, "out.json")
        code, out, err = self.run_cli(["export", "--format", "json", "--period", "2026-01", "--out", out_path])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(out_path))

    def test_existing_add_command_still_works(self):
        code, out, _ = self.run_cli(
            ["add", "--date", "2026-01-05", "--description", "Pay", "--amount", "1500.00", "--category", "salary"]
        )
        self.assertEqual(code, 0)
        self.assertIn("added t1", out)

    def test_existing_balance_command_still_works(self):
        self.run_cli(
            ["add", "--date", "2026-01-05", "--description", "Pay", "--amount", "1500.00", "--category", "salary"]
        )
        code, out, _ = self.run_cli(["balance"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "1500.00")

    def test_split_zero_weight_errors(self):
        code, out, err = self.run_cli(
            ["split", "--date", "2026-01-05", "--description", "X", "--total", "-30.00",
             "--share", "dining=0"]
        )
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("error: "))

    def test_split_output_mentions_added_children(self):
        code, out, err = self.run_cli(
            ["split", "--date", "2026-01-05", "--description", "Dinner", "--total", "-30.00",
             "--share", "dining=1", "--share", "groceries=1"]
        )
        self.assertEqual(code, 0)
        self.assertIn("added", out)


if __name__ == "__main__":
    unittest.main()
