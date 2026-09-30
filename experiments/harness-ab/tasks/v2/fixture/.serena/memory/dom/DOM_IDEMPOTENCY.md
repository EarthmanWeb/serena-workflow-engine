---
name: Idempotency Policy
description: Standing policy for detecting duplicate records by content fingerprint, and for collecting row-level rejections during a bulk input operation, independent of which feature performs the operation. Authoritative — hidden acceptance tests assert on this exactly.
metadata:
  type: domain
---

# DOM_IDEMPOTENCY — Duplicate Detection and Row Rejection

Any feature that ingests a batch of externally-sourced records (a bulk
import, a bulk sync, any "read many records from outside and reconcile
against what's already stored" feature) must be safe to re-run on the same
source without creating duplicate records, and must never silently drop a
malformed row without telling the caller which row it was.

## Record Fingerprint

- Compute a fingerprint for each incoming record as the first **16 hex
  characters** of `sha256("<date ISO>|<amount cents>|<normalized
  description>")` — the SHA-256 hex digest of that pipe-joined string,
  truncated to its first 16 characters.
- `<date ISO>` is the record's date in `YYYY-MM-DD` form.
- `<amount cents>` is the record's signed integer amount in cents, as a
  plain base-10 string (no leading `+`, no thousands separator).
- `<normalized description>` is the description **after** whatever
  normalization this project's own input-normalization rules already
  apply to free-text/category input for that feature (see
  `mem:dom/DOM_INPUT_NORMALIZATION`) — never the raw un-normalized text,
  so two records that normalize to the same thing fingerprint identically.
- The three fields are joined with the literal `|` character, in that
  exact order — reordering the fields or using a different separator
  produces a different, non-interoperable fingerprint.

## Duplicate Handling

- Before creating a record from an incoming item, compute its fingerprint
  and compare against the fingerprints of records already present in the
  target store (recomputed the same way from each existing record's own
  date/amount/description).
- A fingerprint that already exists is a **duplicate**: skip creating a
  new record for it. Never update or merge into the existing record —
  duplicate handling is skip-only, not upsert.
- A fingerprint that does not exist yet: create the record normally.

## Row Rejection

- When a batch operation encounters a malformed row (fails validation for
  any reason — bad shape, invalid field, anything the operation's own
  input rules reject), it must not raise and abort the whole batch. It
  collects that row's **1-based row number** (counting the first data
  row, i.e. excluding a header row if the source format has one, as row
  1. into a rejection list and continues processing the remaining rows.
- The rejection list is returned to the caller as part of the operation's
  result — never only logged, never silently discarded — so the caller
  can see exactly which source rows failed.

## Worked Example (contact sync, illustrative only — not this project's domain)

A hypothetical `contacts` feature syncing a batch of address-book entries
fingerprints each entry as
`sha256("<updated ISO>|<phone digits>|<normalized name>")[:16]`. Running
the same sync twice produces zero new duplicate contacts the second time —
every entry's fingerprint already matches an existing contact, so every
entry is skipped. A row with a missing name is not created and does not
abort the sync; its row number is added to the result's rejection list and
the sync continues with the next row.

Related: `mem:dom/DOM_INPUT_NORMALIZATION` (the normalization applied
before fingerprinting), `mem:ref/REF_ERROR_HANDLING` (this policy is
about _tolerating_ bad rows in a batch, not the error raised for a
single-record operation's invalid input), `mem:arch/ARCH_LEDGERLITE`.
