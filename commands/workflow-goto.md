---
name: workflow-goto
description: Force transition to specific state (debug/recovery)
argument-hint: [STATE]
---

# /workflow-goto [STATE]

Force transition to a specific workflow state.

## Usage

```
/workflow-goto WF_EXECUTE
/workflow-goto WF_CHECKPOINT
```

## Warning

⚠️ This bypasses normal transition validation.
Use only for debugging or recovery.

## Implementation

1. Validate target exists in states.json
2. Warn if transition is unusual
3. Update workflow-state.json with forced flag
4. Add note to WORKING_MEMORY
5. Read target WF_* memory
6. Report: `> **On step [STATE]** (forced)`
