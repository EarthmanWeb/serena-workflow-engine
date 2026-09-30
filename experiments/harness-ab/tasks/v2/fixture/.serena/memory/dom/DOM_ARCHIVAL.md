---
name: Archival Policy
description: Standing policy for where data leaving the active store goes, how the archive file is named, and how repeated archival operations merge into it, independent of which feature performs the archival. Authoritative — hidden acceptance tests assert on this exactly.
metadata:
  type: domain
---

# DOM_ARCHIVAL — Moving Data Out of the Active Store

Any feature that removes records from the project's primary/active data
store because they are no longer needed for day-to-day use (an aging-out
sweep, a cold-storage move, any "data leaves the active store but must
still be recoverable" feature) moves that data into an **archive file**
rather than deleting it outright, following the rules below regardless of
which module performs the move.

## Archive File Naming

- The archive file is named `<store stem>.archive.<fiscal-year>.json`,
  where `<store stem>` is the active store's own filename with its
  extension removed (e.g. an active store at `/data/ledger.json` has stem
  `ledger`), and `<fiscal-year>` is the four-digit fiscal year the
  archived records belong to (see `mem:dom/DOM_FINANCE_CALENDAR` for how
  this project resolves a record's date into a fiscal period; a record's
  fiscal year is the year component of the fiscal period that contains
  its date).
- The archive file lives in the **same directory** as the active store's
  file — the same placement rule this project already uses for its audit
  log (see `mem:dom/DOM_AUDIT`), not the current working directory.
- Records spanning more than one fiscal year in a single archival
  operation are split across one archive file per fiscal year — never
  mixed into one file, never named after only the first or last year.

## Archive File Contents

- The archive file uses this project's standard interchange JSON envelope
  (see `mem:ref/REF_DATA_INTERCHANGE`) with `<kind>` set to the literal
  `"archive"` — i.e. `"schema": "ledgerlite.archive/<api_version>"` — and
  the same key-sorting and signed-decimal-string rules that envelope
  already requires apply here too.
- The current fiscal period (the one `mem:dom/DOM_FINANCE_CALENDAR`
  resolves "today" into) is never archived, regardless of how old any
  individual record's date within it might otherwise make it look — an
  in-progress fiscal period is always left in the active store.

## Append-Merge Behavior

- Archival is append-merge, not overwrite: if the target archive file for
  a given fiscal year already exists (from a prior archival run), newly
  archived records for that same year are merged into its existing
  entries rather than replacing the file.
- After a merge, the archive file's entries are **sorted by date
  ascending, then by id ascending** (the same two-key ordering this
  project already uses for every other record listing — see
  `mem:ref/REF_DATA_INTERCHANGE`) — never append order, never the order
  records were encountered across multiple merge operations.
- A record already present in the archive (same id) is not duplicated by
  a later merge that encounters it again.

## Worked Example (log rotation, illustrative only — not this project's domain)

A hypothetical `logrotate` feature moving old entries out of an active log
store at `/data/events.json` writes them to
`/data/events.archive.2025.json` (fiscal year 2025) and
`/data/events.archive.2026.json` (fiscal year 2026) as two separate files
when the batch spans both years. Running the rotation again later, with
more entries that also fall in fiscal year 2026, merges into the existing
`events.archive.2026.json` — its entries end up sorted by date then id,
with no duplicate ids even though the file already existed.

Related: `mem:dom/DOM_FINANCE_CALENDAR` (fiscal year/period resolution),
`mem:ref/REF_DATA_INTERCHANGE` (envelope shape reused for the archive
file), `mem:dom/DOM_AUDIT` (archive file placement mirrors the audit log's
placement rule), `mem:arch/ARCH_LEDGERLITE`.
