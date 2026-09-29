import contextlib
import io
import os
import tempfile
import unittest

from ledgerlite.cli import main


class TestCliAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")

    def run_cli(self, args):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--file", self.path] + args)
        return code, out.getvalue(), err.getvalue()

    def test_recurring_add_then_list(self):
        code, out, _ = self.run_cli(
            [
                "recurring",
                "add",
                "--description",
                "Rent",
                "--amount",
                "-1500.00",
                "--category",
                "rent",
                "--frequency",
                "monthly",
                "--start",
                "2026-01-01",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("r1", out)

        code, out, _ = self.run_cli(["recurring", "list"])
        self.assertEqual(code, 0)
        self.assertIn("r1  monthly  2026-01-01  -1500.00  rent  Rent", out)

    def test_recurring_add_bad_frequency_errors(self):
        code, out, err = self.run_cli(
            [
                "recurring",
                "add",
                "--description",
                "X",
                "--amount",
                "-10",
                "--category",
                "rent",
                "--frequency",
                "daily",
                "--start",
                "2026-01-01",
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("error: E_BAD_FREQUENCY", err)

    def test_recurring_add_bad_date_range_errors(self):
        code, out, err = self.run_cli(
            [
                "recurring",
                "add",
                "--description",
                "X",
                "--amount",
                "-10",
                "--category",
                "rent",
                "--frequency",
                "monthly",
                "--start",
                "2026-02-01",
                "--end",
                "2026-01-01",
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("error: E_BAD_DATE_RANGE", err)

    def test_budget_set_then_report(self):
        code, _, _ = self.run_cli(
            ["add", "--date", "2026-01-05", "--description", "Groceries", "--amount", "-30.00", "--category", "groceries"]
        )
        self.assertEqual(code, 0)

        code, out, _ = self.run_cli(["budget", "set", "--category", "groceries", "--month", "2026-01", "--limit", "100.00"])
        self.assertEqual(code, 0)
        self.assertIn("budget set: groceries 2026-01 100.00", out)

        code, out, _ = self.run_cli(["budget", "report", "--month", "2026-01"])
        self.assertEqual(code, 0)
        lines = out.strip().split("\n")
        self.assertEqual(lines[0], "CATEGORY  LIMIT  SPENT  REMAINING  STATUS")
        self.assertEqual(lines[1], "groceries  100.00  30.00  70.00  ok")

    def test_budget_report_bad_month_errors(self):
        code, out, err = self.run_cli(["budget", "report", "--month", "bad"])
        self.assertEqual(code, 2)
        self.assertIn("error: E_BAD_MONTH", err)

    def test_budget_report_empty_month_prints_header_only(self):
        code, out, _ = self.run_cli(["budget", "report", "--month", "2026-01"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "CATEGORY  LIMIT  SPENT  REMAINING  STATUS")

    def test_existing_commands_still_work(self):
        code, out, _ = self.run_cli(
            ["add", "--date", "2026-01-05", "--description", "Pay", "--amount", "1500.00", "--category", "salary"]
        )
        self.assertEqual(code, 0)
        code, out, _ = self.run_cli(["balance"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "1500.00")


if __name__ == "__main__":
    unittest.main()
