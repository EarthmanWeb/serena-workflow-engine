---
name: workflow-reset
description: Reset workflow state (requires confirmation)
---

# /workflow-reset

Reset workflow to WF_START state.

## Warning

⚠️ This will:
- Archive current WORKING_MEMORY
- Delete workflow-state.json
- Reset all state tracking

## Confirmation Required

Type "RESET" to confirm.

## Implementation

1. Show current state and warning
2. Require "RESET" confirmation
3. Archive current WORKING_MEMORY (append _archived_timestamp)
4. Delete workflow-state.json
5. Delete workflow-layers.json (if exists)
6. Output: "Workflow reset. Read WF_START to begin."
