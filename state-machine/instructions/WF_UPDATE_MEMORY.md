# WF_UPDATE_MEMORY

> **💾 On step WF_UPDATE_MEMORY**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Update WORKING_MEMORY with progress and state changes.

## Entry

- **From**: WF_REQUIREMENT
- **Triggers**: checkpoint_required, state_change

## Required Actions

1. `update_working_memory` - Write current state to memory
2. `reset_edit_counter` - Clear edit count for checkpoint tracking

## Permissions

- **Edit**: true | **Write**: true
- **Plan Mode**: never

## WORKING_MEMORY Update Format

```markdown
## Progress Tracking
- ✅ [Completed item]
- ⏳ [In progress item]
- ⏸️ [Paused item]

## Last Updated
[Timestamp]
```

## Transitions

| Condition | Next State |
|-----------|------------|
| complete | WF_LOAD_FEATURE |

## RLVR Signal

- **Type**: memory_update | **Impact**: neutral

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Memory updated | `WF_LOAD_FEATURE` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
