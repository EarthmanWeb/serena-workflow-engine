New task: Add bank-statement CSV import and data-retention purge to
`ledgerlite`.

## 1. Bank CSV import (`ledgerlite/importer.py`, CLI `import`)

```python
@dataclass
class ImportResult:
    added: list[Transaction]
    skipped_duplicates: int
    rejected: list[int]


def import_bank_csv(store: Store, path: str) -> ImportResult:
    ...
```

`path` is a CSV file exported by an external bank, with a header row
followed by one data row per bank transaction. Each data row has exactly
four fields, in this order: `date`, `description`, `category`, `amount`.

`import_bank_csv` reads every data row (the header row is never counted
as a data row) and, for each one:

- Parses `date`, `description`, `category`, and `amount` from the row.
- A row is malformed — and must be rejected, not raise — if it does not
  have exactly 4 fields, if `date` does not parse, if `amount` does not
  parse to a valid signed decimal amount, or if `category` (after
  resolving any input alias this project already accepts) is not one of
  this project's allowed categories.
- A row that is not malformed and not a duplicate of a transaction
  already in `store` is added to `store` via the same validated path
  `Store.add_transaction` already uses (so category aliasing, the
  category allow-list, and id assignment all behave exactly as they do
  for a manually-added transaction).
- A row that duplicates a transaction already present (in `store`, or
  already added earlier in the same import call) is not added again.

`import_bank_csv` returns an `ImportResult` with:

- `added`: the list of newly created `Transaction` objects, in the order
  their rows appeared in the file.
- `skipped_duplicates`: the count of rows that were valid but duplicated
  an existing (or already-imported-this-call) transaction.
- `rejected`: the row numbers (1-based, counting only data rows, so the
  first data row is row 1) of every malformed row, in ascending order.

`import_bank_csv` does not raise for a malformed row; it only raises for
conditions unrelated to individual row content — e.g. `path` does not
exist at all.

Import does not overwrite or modify any existing transaction; it only
ever adds new ones or skips.

### CLI: `import --file PATH`

New subcommand `import`, taking the bank CSV's path via `--file` (this is
in addition to the existing global `--file` flag, which continues to name
the ledger's own JSON data file — the CLI must accept both). On success,
save the store and print exactly one line:

```
imported <n_added> (skipped <n_dup>, rejected <n_rejected>)
```

where `<n_added>`, `<n_dup>`, `<n_rejected>` are `len(added)`,
`skipped_duplicates`, and `len(rejected)` respectively.

## 2. Data-retention purge (`ledgerlite/retention.py`, CLI `purge`)

```python
@dataclass
class PurgeResult:
    archived: int
    kept: int
    archive_path: str | None


def purge(store: Store, keep_periods: int, today: date) -> PurgeResult:
    ...
```

`purge` removes from `store` every transaction that is not within the
most recent `keep_periods` fiscal periods counted back from the fiscal
period containing `today` (that current period counts as the first of
the `keep_periods` kept periods), moving each removed transaction into an
archive rather than deleting it outright. Transactions within the kept
window are left untouched in `store`.

`purge` returns a `PurgeResult` with:

- `archived`: the count of transactions removed from `store` and archived.
- `kept`: the count of transactions left in `store` (whether or not they
  were in the kept window before the call — i.e. `store`'s final
  transaction count).
- `archive_path`: the path of the archive file written, or `None` if no
  transaction was archived (nothing to write).

`keep_periods` must be a positive integer; a `keep_periods` of zero or
less is an error.

`purge` persists the mutated store (removed transactions gone, kept ones
remaining) before returning.

### CLI: `purge --keep N`

New subcommand `purge`, taking `--keep N` (a positive integer). "Today"
for the purpose of resolving the retention window is the current UTC
date, unless the environment variable `LEDGERLITE_NOW` is set, in which
case use the date portion of that value instead (this project's existing
code already reads this same variable elsewhere for a deterministic
"now" — reuse that same variable, do not invent a second one). On
success, print exactly one line:

```
purged <archived> (kept <kept>)
```

using the `PurgeResult`'s `archived` and `kept` fields. If nothing was
archived, still print this same line with `archived` as `0`.

## 3. Errors

Both `import_bank_csv` (for the non-row-content failure case above) and
`purge` (for an invalid `keep_periods`) raise domain errors the same way
every other domain-level failure in this project is raised. Reuse an
existing error code where an existing one already fits the condition;
add a new one only if none does.

## 4. Tests

Add your own unit tests for everything you build (import row parsing,
duplicate/reject handling, purge windowing, archive output, CLI
subcommands). Keep all existing tests passing.

---

Work autonomously: skip approval, don't ask me questions, and continue
through to completion. When finished, reply with a short summary of the
files you changed.
