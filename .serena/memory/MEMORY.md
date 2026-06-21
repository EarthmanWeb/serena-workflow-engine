## Critical Rules
- [Plugin Source Location](feedback/FEEDBACK_PLUGIN_SOURCE_LOCATION.md) — this repo IS the plugin source; NEVER write to ~/.claude/plugins/cache/
- [Bypass & Setup Location](feedback/FEEDBACK_BYPASS_AND_SETUP_LOCATION.md) — init gate detects setup in .serena AND legacy .claude; project bypass is user-only (/swe-bypass), un-settable by LLM
- [v4 FSM Redesign](feedback/FEEDBACK_V4_FSM_REDESIGN.md) — reads of WF_* memories do NOT transition state (explicit set_state only); WF_START removed (init → WF_CLASSIFY); WF_VERIFY edit-allowed; arch review is complexity-gated

## Response & Style
- [Response Format](feedback/FEEDBACK_RESPONSE_FORMAT.md) — no conversational language, use functional/direct phrasing only
- [Read docs = list memories](feedback/FEEDBACK_READ_DOCS_MEANS_LIST.md) — "read the docs" means check MEMORY.md and use Serena to list_memories, not external docs

## Browser Session Isolation
- [MCP Browser DevTools](ref/REF_MCP_BROWSER_DEVTOOLS.md) — scenarios-first rule, storageState reuse for parallel agents, tool reference

## Features
- [Feature Index](index/INDEX_FEATURES.md) — Feature registry with relationships and types

## Architecture
- [Architecture Index](arch/ARCH_INDEX.md) — Architecture overview

## Workflow Routing (v4)

Init chain ends at WF_CLASSIFY (WF_START removed). Reading a WF_* memory is a PURE read — it never transitions state; transitions are explicit (`set_state` / prompt-intent hook) only.

| Situation                  | Go To                                         |
| -------------------------- | --------------------------------------------- |
| Simple lookup ("find X")   | `WF_RESEARCH`                                 |
| Starting work (full)       | `WF_INIT` → `WF_CLASSIFY`                      |
| Researching                | `WF_RESEARCH`                                 |
| Making changes (minor patch, ≤5 files) | `WF_CLASSIFY` → `WF_EXECUTE` (arch review skipped) |
| Making changes (new feature / major / >5 files) | `WF_CLASSIFY` → `WF_ARCH_REVIEW` |
| Continuing                 | `WF_CONTINUE`                                 |
| Verifying (may fix in place) | `WF_VERIFY`                                  |

## Memory Types

| Prefix   | Purpose           |
| -------- | ----------------- |
| FEATURE_ | Feature configs   |
| DOM_     | Domain behaviors  |
| SYS_     | System references |
| REF_     | Reference docs    |
| INDEX_   | Navigation        |
| ARCH_    | Architecture      |
| SPEC_    | Specifications    |
| WF_      | Workflow states   |
| WM_      | Session state     |
