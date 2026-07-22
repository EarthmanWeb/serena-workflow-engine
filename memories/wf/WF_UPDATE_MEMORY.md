---
name: WF_UPDATE_MEMORY
description: Workflow step to update or create a non-code memory (DOM_/SYS_/REF_/INDEX_/WM_) and route back.
metadata:
  type: workflow
---

# WF_UPDATE_MEMORY — Update Memory

> **On step WF_UPDATE_MEMORY**

## Use When

- Add or update domain requirements (`DOM_*`).
- Update system or reference docs (`SYS_*`, `REF_*`).
- Create or update index files (`INDEX_*`).
- Update `WM_*` with task progress.
- Capture architectural decisions after `WF_ARCH_REVIEW`.

## Before Updating

- ALWAYS `read_memory("[memory_name]")` before modifying — prevents data loss; forces targeted edits over blind overwrites.
- Find the correct name via `list_memories()` or `INDEX_FEATURES`.

## Steps

### 1. Identify target memory

| Type      | Naming         | Purpose                                       |
| --------- | -------------- | --------------------------------------------- |
| Domain    | `DOM_[DOMAIN]` | User-facing behavior, constraints, edge cases |
| System    | `SYS_[SYSTEM]` | System documentation                          |
| Reference | `REF_[TOPIC]`  | Reference documentation                       |
| Index     | `INDEX_[TYPE]` | File/symbol indexes                           |
| Working   | `WM_*`         | Session task state                            |

### 2. WM updates

- Invoke `/swe-wm-update --from {calling_step}`. The skill reads, validates, and writes WM with the full checklist and template. Do NOT hand-write WM.

### 3. Non-WM memory updates

Use Serena tools directly:

- `mcp__plugin_swe_serena__write_memory("MEMORY_NAME", "content")`
- `mcp__plugin_swe_serena__edit_memory("MEMORY_NAME", "old", "new", "literal")`

### 3b. Keep MEMORY.md a terse index

`MEMORY.md` loads into context every session. Keep it lean (aim **< 200 lines**). When a new memory needs an index entry:

- Add exactly **one line**: `- [Title](path) — short hook` (**≤ 200 chars**).
- Put detail in the linked topic file, NOT in MEMORY.md. NEVER paste a summary.
- Group entries under category headers (≤6). Do NOT add a `##` section per memory.
- Do NOT index `spec/`, `report/`, `research/`, or `project/` memories — browse those with `list_memories(topic="…")`.
- The `write_memory` PostToolUse hook warns when MEMORY.md exceeds its size budget, an entry is over-long, or a non-indexed category leaked in. Trim on the warning.

### 4. Confirm to user

- Report: `Updated [MEMORY_NAME] with: [brief description]`.

## Routing

| Condition             | Next Step                        |
| --------------------- | -------------------------------- |
| Domain memory updated | `WF_CLASSIFY`                    |
| WM updated            | Return to previous workflow step |

- Update WM via `/swe-wm-update` before transitioning.
