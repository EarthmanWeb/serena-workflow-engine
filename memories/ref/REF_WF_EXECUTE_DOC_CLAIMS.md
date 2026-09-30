---
name: WF_EXECUTE Doc Claims Ledger Format
description: Row format and parser API for the Doc Claims Ledger tracked in WM during WF_EXECUTE — open when recording or updating a claim row.
obligations:
  - Record one ledger row on first use of any actionable value taken from a memory; WF_VERIFY/WF_DONE are BLOCKED while any row is pending.
metadata:
  type: reference
---

# Doc Claims Ledger — Row Format & Parser

Track every actionable value taken from a memory in the WM section `## Doc Claims Used`.

- Rule: when a memory supplies an actionable value (URL, domain, path, container name, command, version, class mapping), record ONE ledger row on FIRST use as `pending`. Update the row to `confirmed` when the action using it succeeds, or to `corrected → <true value>` after fixing the memory.
- `WF_VERIFY` and `WF_DONE` are BLOCKED while any row is `pending`.

Row format (exact, one per claim):

```markdown
- mem:<memory-name> → <claim-value> → pending
- mem:<memory-name> → <claim-value> → confirmed
- mem:<memory-name> → <claim-value> → corrected → <true value>
```

- The parser tolerates `->` as well as `→`.
- Shared parser: `hooks/swe_hooks/core/doc_claims.py` — `parse_claims(wm_content) -> list[dict]` returns `{"name","claim","status","true_value"}` (`true_value` is `None` unless corrected); `pending_claims(wm_content) -> list[dict]` returns `"pending"` rows; `blocking_claims(wm_content) -> list[dict]` returns the VERIFY/DONE blocking set.
- A `corrected` row MUST record the true value (`corrected → <true value>`) or it BLOCKS WF_VERIFY/WF_DONE like a pending row. Mark `corrected` ONLY after the actual memory edit — status without the edit is a violation checked at WF_VERIFY.
