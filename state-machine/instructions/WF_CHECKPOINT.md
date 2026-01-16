# WF_CHECKPOINT

> **💾 On step WF_CHECKPOINT**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Save progress checkpoint during extended execution.

## Entry

- **From**: WF_EXECUTE
- **Triggers**: edits_threshold, manual_checkpoint

## Required Actions

1. `update_working_memory` - Save current progress state
2. `reset_edit_counter` - Clear edit count
3. `summarize_progress` - Brief summary of what's done

## Permissions

- **Edit**: true | **Write**: true
- **Plan Mode**: never

## Checkpoint Content

```markdown
## Checkpoint - [Timestamp]

### Completed
- [List of completed changes]

### In Progress
- [Current work item]

### Remaining
- [Items still to do]
```

## Transitions

| Condition | Next State |
|-----------|------------|
| continue | WF_EXECUTE |
| complete | WF_VERIFY |

## RLVR Signal

- **Type**: checkpoint | **Impact**: penalty_if_forced (-0.05)

Forced checkpoints (due to hitting threshold) indicate large changes that may need breaking down.

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| More work to do | `WF_EXECUTE` |
| All changes done | `WF_VERIFY` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
