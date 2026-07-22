---
name: Memory Index
description: Root index of project memories for serena-workflow-engine
metadata:
  type: index
---

## Critical Rules
- [Plugin Source Location](feedback/FEEDBACK_PLUGIN_SOURCE_LOCATION.md) — this repo IS the plugin source; NEVER write to ~/.claude/plugins/cache/
- [Bypass & Setup Location](feedback/FEEDBACK_BYPASS_AND_SETUP_LOCATION.md) — init gate detects setup in .serena AND legacy .claude; project bypass is user-only (/swe-bypass), un-settable by LLM
- [v4 FSM Redesign](feedback/FEEDBACK_V4_FSM_REDESIGN.md) — WF_* reads never transition state (explicit set_state only); WF_START removed; arch review is complexity-gated

## Response & Style
- [Response Format](feedback/FEEDBACK_RESPONSE_FORMAT.md) — no conversational language, use functional/direct phrasing only
- [Read docs = list memories](feedback/FEEDBACK_READ_DOCS_MEANS_LIST.md) — "read the docs" means check MEMORY.md and use Serena to list_memories, not external docs

## Development
- [Development Standards](feature/FEATURE_DEV_STANDARDS.md) — project overview, per-language conventions, build/format/git commands
- [Test Suite](feature/FEATURE_TESTS.md) — verification approach + task-completion checklist

## Reference
- [Memory Style Standard](ref/REF_MEMORY_STYLE.md) — MANDATORY terse-imperative machine-readable style for ALL memories; enforced by swe_post_memory_style.py hook + /swe-memory-audit
- [MCP Browser DevTools](ref/REF_MCP_BROWSER_DEVTOOLS.md) — scenarios-first rule, storageState reuse for parallel agents, tool reference
- [Memory Maintenance](ref/REF_MEMORY_MAINTENANCE.md) — how memories are created & maintained (discovery model, style, threshold, actions)

## Features
- [Feature Index](index/INDEX_FEATURES.md) — Feature registry with relationships and types

## Architecture
- [Architecture Index](arch/ARCH_INDEX.md) — Architecture overview
- [Init memory-paths & Serena reconnect](dom/DOM_SWE_INIT_MEMORY_PATHS.md) — conf writes only ./.serena/memory (singular); Serena must reconnect after bootstrap or memories split-brain
- [Two Memory Trees](dom/DOM_MEMORY_TREES.md) — plugin SOURCE (memories/, ships everywhere) vs this repo's OWN dev memories (.serena/memory/, local); edit source as files, dev via Serena tools

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
