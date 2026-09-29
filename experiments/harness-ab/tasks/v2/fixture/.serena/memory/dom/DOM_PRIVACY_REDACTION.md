---
name: Privacy Redaction
description: PII redaction rules applied to transaction descriptions in exports only. Authoritative — hidden acceptance tests grade against this exactly.
metadata:
  type: domain
---

# DOM_PRIVACY_REDACTION — Description Redaction (Exports Only)

Transaction descriptions may contain sensitive numbers a user pasted in
(card numbers, account numbers, SSNs). ledgerlite never modifies stored
data or interactive output — redaction is applied **only** when rendering
an export (CSV or JSON via `mem:dom/DOM_EXPORT_FORMATS`). The `Store`, the
`list`/`statement` CLI output, and `render_statement` all show the
**original, unredacted** description.

## Rules (apply in this order)

1. **SSN marker** (apply this rule first): the case-insensitive word
   `"ssn"`, followed by any non-digit separator (colon, `#`, space, etc.)
   and then a run of digits, has the entire `"ssn ... digits"` span
   replaced with the literal string `"SSN:REDACTED"`. Example:
   `"SSN: 123456789"` → `"SSN:REDACTED"`, `"ssn#987654321 on file"` →
   `"SSN:REDACTED on file"`.
2. **Long numbers**: any run of **12 to 19 consecutive digits** remaining
   after step 1 is replaced with `"****"` followed by that run's own last 4
   digits. Example: `"card 1234567890123456"` → `"card ****3456"`. A run of
   11 digits or fewer, or 20 or more, is left untouched.
3. Text with neither pattern is returned unchanged.

## Scope

- Redaction touches **descriptions only** — never `category`, `id`, `date`,
  or `amount`.
- Redaction is applied at export time (inside `export_csv`/`export_json`),
  not when the transaction or split child is created or saved.

Related: `mem:dom/DOM_EXPORT_FORMATS` (where redaction is applied).
