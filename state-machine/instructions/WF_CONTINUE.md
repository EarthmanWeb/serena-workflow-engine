# WF_CONTINUE

> **▶️ On step WF_CONTINUE**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Resume from existing WORKING_MEMORY.

## Entry

- **From**: WF_START
- **Triggers**: working_memory_exists

## Required Actions

1. `read_working_memory` - Load existing WORKING_MEMORY file
2. `restore_context` - Understand previous progress and state
3. `determine_next_step` - Identify where to resume

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: never

## Resume Point Detection

Check WORKING_MEMORY for:
- Last completed step
- Current task status
- Any blockers noted
- Layers involved (for multi-layer detection)

**Multi-layer detection**: If multiple architectural layers in WORKING_MEMORY → route to WF_ARCH_REVIEW

## Transitions

| Condition | Next State |
|-----------|------------|
| arch_review | WF_ARCH_REVIEW |
| execute | WF_EXECUTE |
| needs_clarification | WF_CLARIFY |
| reclassify | WF_CLASSIFY |

## RLVR Signal

- **Type**: resume | **Impact**: neutral

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Was executing (multi-layer) | `WF_ARCH_REVIEW` |
| Was executing (single-layer) | `WF_EXECUTE` |
| Was blocked/unclear | `WF_CLARIFY` |
| No previous state | `WF_CLASSIFY` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
