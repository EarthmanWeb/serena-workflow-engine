---
name: swe-reset
description: Reset workflow state (requires confirmation)
---

# /swe-reset

Reset workflow to WF_START state. Clears all session state including sentinels,
decoupled state files, and working memory.

## Warning

⚠️ This will:

- Archive current WORKING_MEMORY
- Delete init gate sentinels (`.serena/streams/.init_*`)
- Delete decoupled state files (`.serena/swe-state/*.state`)
- Reset all state tracking

## Implementation

Execute immediately without confirmation:

1. Archive current WORKING_MEMORY (append `_archived_YYYYMMDD_HHMMSS`)
2. Delete init gate sentinels: `rm -f .serena/streams/.init_*`
3. Delete decoupled state files: `rm -f .serena/swe-state/*.state`
4. Output: "Workflow reset. Read WF_INIT to begin."

## Recovery Use Case

When the LLM hits the init gate deadlock (sentinel missing, daemon blocks
re-init), `/swe-reset` clears all state so the next init chain starts clean.
The self-healing code in the init gate and prompt hook should handle most
cases automatically, but `/swe-reset` is the manual escape hatch.
