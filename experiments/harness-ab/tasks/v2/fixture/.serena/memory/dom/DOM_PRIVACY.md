---
name: Privacy Policy
description: Standing policy for redacting sensitive numbers from any data this project produces for consumption outside the app. Authoritative — hidden acceptance tests assert on this exactly.
metadata:
  type: domain
---

# DOM_PRIVACY — Redaction of Sensitive Numbers

Free-text fields a user enters (descriptions, notes, memos) may contain
sensitive numbers pasted in by mistake — card numbers, account numbers,
government identifiers. This project never modifies what it stores or
what it shows interactively. Redaction is applied **only** at the moment
data is rendered into a file meant to leave the application (see
`mem:ref/REF_DATA_INTERCHANGE`) — never inside the primary data store,
never in any interactive/CLI display, never in an on-screen report.

## Rules (apply in this order)

1. **Identifier marker** (apply this rule first, before rule 2): the
   case-insensitive literal word `"ssn"`, followed by any run of
   non-digit characters (a colon, a `#`, a space, or any combination), and
   then a run of digits, has the entire matched span — from the start of
   `"ssn"` through the end of that digit run — replaced with the literal
   string `"SSN:REDACTED"`. Example: the text `"SSN: 123456789"` becomes
   `"SSN:REDACTED"`; the text `"ssn#987654321 on file"` becomes
   `"SSN:REDACTED on file"`.
2. **Long number runs**: after rule 1 has been applied, any remaining run
   of **12 to 19 consecutive digits** (inclusive on both ends) is replaced
   with the literal string `"****"` followed by that run's own last 4
   digits. Example: `"card 1234567890123456"` becomes `"card ****3456"`. A
   run of 11 digits or fewer, or 20 digits or more, is left untouched by
   this rule.
3. Text matching neither rule is returned completely unchanged.

## Scope

- Redaction touches only free-text description/note fields — never an
  identifier, a date, a category/label, or a monetary amount field.
- Redaction happens at the moment of producing the outbound file, not
  when the underlying record is first created or saved.

Related: `mem:ref/REF_DATA_INTERCHANGE` (where redaction is applied).
