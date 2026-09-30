import filecmp
import json
import os
import tempfile
import unittest

from ledgerlite.store import Store


V1_CONTENT = {
    "schema_version": 1,
    "transactions": [
        {
            "id": "t1",
            "date": "2026-01-05",
            "description": "Groceries",
            "amount_cents": -1234,
            "category": "groceries",
        }
    ],
    "some_unknown_key": {"nested": True, "value": 42},
}


class TestMigration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "ledger.json")
        with open(self.path, "w") as f:
            json.dump(V1_CONTENT, f, indent=2)
            f.write("\n")
        with open(self.path, "rb") as f:
            self.original_bytes = f.read()

    def test_migration_creates_backup(self):
        store = Store(self.path)
        store.load()
        backup_path = self.path + ".v1.bak"
        self.assertTrue(os.path.exists(backup_path))

    def test_backup_is_byte_identical_to_original(self):
        store = Store(self.path)
        store.load()
        backup_path = self.path + ".v1.bak"
        with open(backup_path, "rb") as f:
            backup_bytes = f.read()
        self.assertEqual(backup_bytes, self.original_bytes)

    def test_migrated_file_has_schema_v2_and_new_keys(self):
        store = Store(self.path)
        store.load()
        with open(self.path) as f:
            data = json.load(f)
        self.assertEqual(data["schema_version"], 2)
        self.assertIn("recurring", data)
        self.assertIn("budgets", data)
        self.assertEqual(data["recurring"], [])
        self.assertEqual(data["budgets"], {})

    def test_unknown_top_level_keys_preserved(self):
        store = Store(self.path)
        store.load()
        with open(self.path) as f:
            data = json.load(f)
        self.assertEqual(data["some_unknown_key"], {"nested": True, "value": 42})

    def test_transactions_preserved_after_migration(self):
        store = Store(self.path)
        store.load()
        self.assertEqual(len(store.transactions), 1)
        self.assertEqual(store.transactions[0].id, "t1")
        self.assertEqual(store.transactions[0].amount_cents, -1234)

    def test_second_load_is_idempotent_no_duplicate_backup_overwrite(self):
        store = Store(self.path)
        store.load()
        backup_path = self.path + ".v1.bak"
        with open(backup_path, "rb") as f:
            backup_after_first_load = f.read()

        # Load again with a fresh Store — file is now v2, should not re-migrate.
        store2 = Store(self.path)
        store2.load()
        with open(self.path) as f:
            data = json.load(f)
        self.assertEqual(data["schema_version"], 2)

        with open(backup_path, "rb") as f:
            backup_after_second_load = f.read()
        self.assertEqual(backup_after_first_load, backup_after_second_load)

    def test_add_recurring_and_budget_persist_across_reload(self):
        from datetime import date

        from ledgerlite.recurring import RecurringRule

        store = Store(self.path)
        store.load()
        rule = RecurringRule(
            id="",
            description="rent",
            amount_cents=-150000,
            category="rent",
            frequency="monthly",
            start=date(2026, 1, 1),
        )
        store.add_recurring(rule)
        store.set_budget("rent", "2026-01", 200000)
        store.save()

        reloaded = Store(self.path)
        reloaded.load()
        self.assertEqual(len(reloaded.list_recurring()), 1)
        self.assertEqual(reloaded.get_budget("rent", "2026-01"), 200000)


if __name__ == "__main__":
    unittest.main()
