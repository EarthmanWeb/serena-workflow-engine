---
name: Audit Policy
description: Standing policy for logging any operation that writes a file outside the primary data store, independent of which feature performs the write. Authoritative — hidden acceptance tests assert on this exactly.
metadata:
  type: domain
---

# DOM_AUDIT — External Write Audit Trail

Any operation that writes a file **outside** the project's primary data
store (the JSON ledger file) — an export, a generated report saved to
disk, or any future "write to an external path" feature — must append
exactly one line to an audit log, in addition to performing its own write.
This applies regardless of which module performs the write.

## Audit Log Location

- The audit log file is named `.ledgerlite-audit.log`.
- It lives in the **same directory as the primary data store's file**
  (i.e. `os.path.dirname` of the store's own path), not the current
  working directory and not next to the file being written.
- Create the audit log file if it does not yet exist; every subsequent
  operation appends to it — never truncate or overwrite it.

## Audit Line Format

- Exactly one line per audited operation, with no trailing whitespace
  beyond the newline:
  ```
  <ISO8601 UTC timestamp>|<operation>|<detail 1>|<detail 2>|...
  ```
- Field order: the ISO 8601 UTC timestamp always comes first, then the
  operation's name (the lowercase name of the feature performing the
  write, e.g. the name used in that feature's own CLI subcommand or
  function name), then that operation's own detail fields **in the same
  order that operation's own specification lists its inputs/outputs**,
  each separated by the same `|` delimiter.
- The final detail field for any write that produces a record count is
  that count, as a plain integer with no leading zeros.

## Timestamp Source

- If the environment variable `LEDGERLITE_NOW` is set, use its value
  **verbatim** as the timestamp (this exists so tests can produce
  deterministic output — never reformat or re-parse it).
- Otherwise, use the current UTC time formatted as `%Y-%m-%dT%H:%M:%SZ`
  (ISO 8601, second precision, literal `Z` suffix, no microseconds, no
  UTC offset notation other than `Z`).

## Worked Example (illustrative only — not this project's domain)

A hypothetical `backup` feature that writes 42 records to an external path
would append a line such as `2026-03-01T09:00:00Z|backup|42` — timestamp
first, then the operation name `backup`, then that operation's own detail
fields in its own specified order.

Related: `mem:ref/REF_DATA_INTERCHANGE` (the files whose writes this audit
trail records), `mem:ref/REF_ERROR_HANDLING`.
