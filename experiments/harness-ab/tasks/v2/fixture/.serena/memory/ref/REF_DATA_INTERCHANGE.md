---
name: Data Interchange Standard
description: Standing byte-level format for every file this project writes for consumption outside the app (CSV and JSON), independent of which feature produces the file. Authoritative — hidden acceptance tests assert on these formats byte-for-byte.
metadata:
  type: reference
---

# REF_DATA_INTERCHANGE — External File Format Standard

Any file this project writes for a consumer outside the application itself
(a downstream import, a third-party report, any "export"-shaped feature)
must follow this standard exactly, regardless of which feature produces
it. Neither format matches a language runtime's library defaults — every
deviation below is intentional and applies project-wide.

## CSV Files

- **Delimiter**: semicolon (`;`), never comma.
- **Header row**: a CSV file's header row uses the exact, case-sensitive
  column names the feature's own specification defines, in the order that
  specification lists them, separated by the semicolon delimiter above.
- **Date fields**: `DD.MM.YYYY` (e.g. `20.01.2026`), never ISO 8601.
- **Signed decimal fields** (e.g. monetary amounts): a comma as the
  decimal separator (e.g. `12,34`, not `12.34`), with a leading `-` for
  negative values and no sign character for non-negative values. Example:
  a negative value of magnitude 5.00 is written `-5,00`; a non-negative
  value of the same magnitude is written `5,00`.
- **Encoding**: UTF-8 **with a byte-order mark** (`\xef\xbb\xbf` at the
  start of the file).
- **Line endings**: CRLF (`\r\n`) for every row, including the header.
- Rows are ordered by the data's natural primary ordering used elsewhere
  in the project (e.g. chronological, then by identifier) — never
  insertion order or an unspecified order.

## JSON Files

- Top-level envelope shape:
  ```json
  {
    "schema": "ledgerlite.<kind>/<api_version>",
    "...": "..."
  }
  ```
  `<kind>` is the lowercase name of the module/feature producing the file
  (e.g. a file produced by this project's `export` feature uses
  `"ledgerlite.export/<api_version>"`). The current `<api_version>` for
  this project's external JSON envelope is **3**; bump it only when the
  envelope's shape changes in a way existing consumers cannot parse.
- Every JSON object's keys are written **sorted alphabetically** (e.g.
  `sort_keys=True` to `json.dump`, or the equivalent in another runtime) —
  this applies to the envelope and to every nested object.
- Monetary or other signed-decimal values inside a JSON file are rendered
  as **decimal strings** (e.g. `"-5.00"`, `"12.34"`), never as raw integer
  cents and never as a JSON number, so downstream consumers never lose
  precision to floating point.

## Worked Example (invoice export, illustrative only — not this project's domain)

An `invoicing` module's export of one line item at 5.00, negative
(a credit), renders in CSV as a semicolon-delimited row containing
`-5,00`, and in JSON as `{"amount": "-5.00", ...}` inside an envelope
`{"schema": "ledgerlite.invoicing/3", ...}` with every object's keys
alphabetically sorted.

## Refusing to Overwrite

- Any function that writes one of these files takes a `force` flag,
  default `False`. If the destination path already exists and `force` is
  not set, the write must fail without modifying the existing file — see
  `mem:ref/REF_ERROR_HANDLING` for how to signal this. `force=True`
  overwrites unconditionally.
- Any CLI surface for such a write exposes this as a `--force` flag.
- Requesting an unsupported output format is also an error — see
  `mem:ref/REF_ERROR_HANDLING`.

Related: `mem:dom/DOM_FINANCE_CALENDAR` (period bounds used inside a
period-scoped export's envelope), `mem:dom/DOM_PRIVACY` (redaction applied
before writing), `mem:dom/DOM_INPUT_NORMALIZATION` (canonical keys used in
output), `mem:dom/DOM_AUDIT` (the audit trail every such write leaves),
`mem:ref/REF_ERROR_HANDLING`.
