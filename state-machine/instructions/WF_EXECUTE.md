# WF_EXECUTE

> **⚡ On step WF_EXECUTE**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Execute implementation changes.

## Entry

- **From**: WF_ASK_PERMISSION, WF_SWARM_ORCHESTRATE, WF_DEBUG_TDD, WF_CHECKPOINT
- **Triggers**: permission_granted, swarm_complete, debug_fixed

## Required Actions

1. `implement_changes` - Make the approved code changes
2. `follow_standards` - Adhere to REF_DEV_STANDARDS
3. `track_edits` - Count edits for checkpoint threshold

## Permissions

- **Edit**: true | **Write**: true
- **Plan Mode**: never

## Execution Guidelines

- Follow KISS > DRY > YAGNI priority
- Use Serena symbolic tools when possible
- Track edit count (checkpoint at threshold)
- Update WORKING_MEMORY after significant progress

## Edit Tracking

After ~5 significant edits, transition to WF_CHECKPOINT.

## Transitions

| Condition | Next State |
|-----------|------------|
| checkpoint_needed | WF_CHECKPOINT |
| complete | WF_VERIFY |

## RLVR Signal

- **Type**: execution_step | **Impact**: neutral

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Edit threshold reached | `WF_CHECKPOINT` |
| Implementation complete | `WF_VERIFY` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
