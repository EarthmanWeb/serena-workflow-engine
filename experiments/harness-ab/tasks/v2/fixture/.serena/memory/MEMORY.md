<!--
MEMORY.md is an INDEX, not a content store. It loads into context every session,
so keep it lean — aim for < 200 lines.
  • One line per memory: `- [Title](path) — short hook` (≤ 200 chars).
  • The detail lives in the linked topic file, NOT here. Never paste a summary in.
  • Group entries under a few category headers — do NOT add a `##` section per memory.
-->

## Features
- [Feature Index](index/INDEX_FEATURES.md) — Feature registry

## Ledger

- [Ledger Architecture](arch/ARCH_LEDGERLITE.md) — modules, layering, data flow, file layout, standing-standards index
- [Ledger Domain Rules](dom/DOM_LEDGER_RULES.md) — amount parsing, fixed category set (READ BEFORE editing domain logic)
- [Finance Calendar Policy](dom/DOM_FINANCE_CALENDAR.md) — fiscal period bounds for any period-scoped feature (READ BEFORE period-scoped work)
- [Money Distribution Policy](dom/DOM_MONEY_DISTRIBUTION.md) — weighted-distribution algorithm + derived-record naming (READ BEFORE any weight-based split/allocation work)
- [Data Interchange Standard](ref/REF_DATA_INTERCHANGE.md) — exact CSV/JSON format for files produced for outside consumption (READ BEFORE export/report-to-file work)
- [Privacy Policy](dom/DOM_PRIVACY.md) — sensitive-number redaction rules for outbound data (READ BEFORE export/report-to-file work)
- [Input Normalization Policy](dom/DOM_INPUT_NORMALIZATION.md) — category alias acceptance on input (READ BEFORE adding a category-accepting entry point)
- [Error Handling Standard](ref/REF_ERROR_HANDLING.md) — error code naming scheme + CLI error contract
- [Audit Policy](dom/DOM_AUDIT.md) — audit-log requirement for writes outside the primary data store
- [Report Style Guide](ref/REF_REPORT_STYLE.md) — text-report rendering conventions
- [Test Suite](feature/FEATURE_TESTS.md) — how to run tests
- [Dev Standards](feature/FEATURE_DEV_STANDARDS.md) — stdlib only, Decimal, dataclasses, error codes

## Workflow Routing

| Situation                  | Go To          |
| --------------------------- | -------------- |
| Simple lookup ("find X")    | `WF_RESEARCH`  |
| Starting work (full)        | `WF_INIT`      |
| Making changes               | `WF_CLASSIFY`  |
| Continuing                   | `WF_CONTINUE`  |
| Verifying                    | `WF_VERIFY`    |

## Memory Types

| Prefix   | Purpose           |
| -------- | ----------------- |
| FEATURE_ | Feature configs   |
| DOM_     | Domain behaviors  |
| REF_     | Reference docs    |
| ARCH_    | Architecture      |
| INDEX_   | Navigation        |
