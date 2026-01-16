---
name: swe-status
description: Display current workflow state and valid transitions
---

# /swe-status

Display current workflow state information.

## Output

```
================================================================================
WORKFLOW STATUS
================================================================================
Session ID:     [session_id]
Current State:  [WF_STATE]
Previous State: [WF_STATE]
Plan Mode:      [true/false]

Working Memory: [WORKING_MEMORY_file]
Feature(s):     [active features]

Edits Since Checkpoint: [count]/3

Valid Transitions:
  → [state1]
  → [state2]

State History (last 5):
  1. [state]
  2. [state]
  ...

RLVR Trajectory: [trajectory_id]
Steps: [count]
================================================================================
```

## Implementation

1. Parse `.claude/workflow-state.json`
2. Read current WORKING_MEMORY
3. Load valid transitions from `state-machine/states.json`
4. Display formatted output
