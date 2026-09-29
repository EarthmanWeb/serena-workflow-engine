import contextlib
import io
import os
import tempfile
import unittest

from ledgerlite.cli import main


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")

    def run_cli(self, args):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--file", self.path] + args)
        return code, out.getvalue(), err.getvalue()

    def test_add_then_balance(self):
        code, out, _ = self.run_cli(
            ["add", "--date", "2026-01-05", "--description", "Pay", "--amount", "1500.00", "--category", "salary"]
        )
        self.assertEqual(code, 0)
        self.assertIn("added t1", out)

        code, out, _ = self.run_cli(["balance"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "1500.00")

    def test_list_empty(self):
        code, out, _ = self.run_cli(["list"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_add_invalid_category_errors(self):
        code, out, err = self.run_cli(
            ["add", "--date", "2026-01-05", "--description", "X", "--amount", "-5", "--category", "bogus"]
        )
        self.assertEqual(code, 2)
        self.assertIn("error: E_UNKNOWN_CATEGORY", err)

    def test_add_invalid_amount_errors(self):
        code, out, err = self.run_cli(
            ["add", "--date", "2026-01-05", "--description", "X", "--amount", "abc", "--category", "other"]
        )
        self.assertEqual(code, 2)
        self.assertIn("error: E_INVALID_AMOUNT", err)

    def test_list_filters_by_month(self):
        self.run_cli(["add", "--date", "2026-01-05", "--description", "Jan", "--amount", "-1", "--category", "other"])
        self.run_cli(["add", "--date", "2026-02-05", "--description", "Feb", "--amount", "-1", "--category", "other"])
        code, out, _ = self.run_cli(["list", "--month", "2026-01"])
        self.assertEqual(code, 0)
        self.assertIn("Jan", out)
        self.assertNotIn("Feb", out)


if __name__ == "__main__":
    unittest.main()
