## Critical Rules
- [Plugin Source Location](feedback/FEEDBACK_PLUGIN_SOURCE_LOCATION.md) — this repo IS the plugin source; NEVER write to ~/.claude/plugins/cache/
- [Bypass & Setup Location](feedback/FEEDBACK_BYPASS_AND_SETUP_LOCATION.md) — init gate detects setup in .serena AND legacy .claude; project bypass is user-only (/swe-bypass), un-settable by LLM

## Response & Style
- [Response Format](feedback/FEEDBACK_RESPONSE_FORMAT.md) — no conversational language, use functional/direct phrasing only
- [Read docs = list memories](feedback/FEEDBACK_READ_DOCS_MEANS_LIST.md) — "read the docs" means check MEMORY.md and use Serena to list_memories, not external docs

## Browser Session Isolation
- [MCP Browser DevTools](ref/REF_MCP_BROWSER_DEVTOOLS.md) — scenarios-first rule, storageState reuse for parallel agents, tool reference

## Features
- [Feature Index](index/INDEX_FEATURES.md) — Feature registry with relationships and types

## Architecture
- [Architecture Index](arch/ARCH_INDEX.md) — Architecture overview

## Workflow Routing

| Situation                  | Go To                                         |
| -------------------------- | --------------------------------------------- |
| Simple lookup ("find X")   | `WF_RESEARCH`                                 |
| Starting work (full)       | `WF_INIT`                                     |
| Researching                | `WF_RESEARCH`                                 |
| Making changes             | `WF_CLASSIFY`                                 |
| Continuing                 | `WF_CONTINUE`                                 |
| Verifying                  | `WF_VERIFY`                                   |

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
