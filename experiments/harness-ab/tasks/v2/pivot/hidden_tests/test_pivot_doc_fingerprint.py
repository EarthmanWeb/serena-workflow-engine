"""Doc-only: idempotency policy (dom/DOM_IDEMPOTENCY) fingerprint formula
-- sha256("<date ISO>|<amount cents>|<normalized description>")[:16],
duplicates skipped never updated."""

import hashlib
import os
import tempfile
import unittest
from datetime import date

from ledgerlite.importer import import_bank_csv
from ledgerlite.store import Store

_HEADER = "date;description;category;amount"


def _write_csv(path, data_lines):
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write(_HEADER + "\r\n")
        for line in data_lines:
            f.write(line + "\r\n")


class TestFingerprintFormula(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "ledger.json")
        self.store = Store(self.store_path)
        self.store.load()
        self.csv_path = os.path.join(self.tmpdir, "bank.csv")

    def test_first_import_matches_expected_fingerprint(self):
        # sha256("2026-01-05|-450|coffee")[:16]
        expected = hashlib.sha256(b"2026-01-05|-450|coffee").hexdigest()[:16]
        _write_csv(self.csv_path, ["05.01.2026;coffee;dining;-4,50"])
        import_bank_csv(self.store, self.csv_path)
        tx = self.store.transactions[0]
        actual = hashlib.sha256(
            f"{tx.date.isoformat()}|{tx.amount_cents}|{tx.description}".encode()
        ).hexdigest()[:16]
        self.assertEqual(actual, expected)

    def test_reimporting_same_file_produces_zero_new_transactions(self):
        _write_csv(self.csv_path, ["05.01.2026;coffee;dining;-4,50"])
        import_bank_csv(self.store, self.csv_path)
        result2 = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(result2.added, [])
        self.assertEqual(result2.skipped_duplicates, 1)
        self.assertEqual(len(self.store.transactions), 1)

    def test_duplicate_within_same_import_call_skipped(self):
        _write_csv(
            self.csv_path,
            [
                "05.01.2026;coffee;dining;-4,50",
                "05.01.2026;coffee;dining;-4,50",
            ],
        )
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(len(result.added), 1)
        self.assertEqual(result.skipped_duplicates, 1)

    def test_different_date_not_a_duplicate(self):
        self.store.add_transaction(date(2026, 1, 5), "coffee", -450, "dining")
        _write_csv(self.csv_path, ["06.01.2026;coffee;dining;-4,50"])
        result = import_bank_csv(self.store, self.csv_path)
        self.assertEqual(len(result.added), 1)
        self.assertEqual(result.skipped_duplicates, 0)

    def test_duplicate_is_skipped_never_updated(self):
        # Existing store transaction and an incoming row with the same
        # date/amount/description fingerprint: the existing record's
        # identity is preserved (skip-only, never upsert).
        existing = self.store.add_transaction(date(2026, 1, 5), "coffee", -450, "dining")
        _write_csv(self.csv_path, ["05.01.2026;coffee;dining;-4,50"])
        import_bank_csv(self.store, self.csv_path)
        self.assertEqual(len(self.store.transactions), 1)
        self.assertIs(self.store.transactions[0], existing)


if __name__ == "__main__":
    unittest.main()
