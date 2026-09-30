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

- [Ledger Architecture](feature/FEATURE_LEDGER.md) — modules, data flow, file layout
- [Ledger Domain Rules](dom/DOM_LEDGER_RULES.md) — validation, categories, error codes (READ BEFORE editing domain logic)
- [CLI Output Formats](ref/REF_CLI_OUTPUT.md) — exact stdout/stderr formats (graded by tests)
- [Test Suite](feature/FEATURE_TESTS.md) — how to run tests
- [Dev Standards](feature/FEATURE_DEV_STANDARDS.md) — stdlib only, Decimal, dataclasses, error codes

## Workflow Routing

| Situation                | Go To         |
| ------------------------ | ------------- |
| Simple lookup ("find X") | `WF_RESEARCH` |
| Starting work (full)     | `WF_INIT`     |
| Making changes           | `WF_CLASSIFY` |
| Continuing               | `WF_CONTINUE` |
| Verifying                | `WF_VERIFY`   |

## Memory Types

| Prefix   | Purpose          |
| -------- | ---------------- |
| FEATURE_ | Feature configs  |
| DOM_     | Domain behaviors |
| REF_     | Reference docs   |
| INDEX_   | Navigation       |
