# WF_ASK_PERMISSION

> **🔐 On step WF_ASK_PERMISSION**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Request permission for significant changes before execution.

## Entry

- **From**: WF_ARCH_REVIEW
- **Triggers**: architecture_approved

## Required Actions

1. `summarize_planned_changes` - Brief overview of what will change
2. `list_affected_files` - Enumerate files to be modified
3. `request_confirmation` - Get explicit "yes" from user

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: never

## Permission Request Format

```markdown
## Planned Changes

### Summary
[Brief description of changes]

### Files to Modify
- `path/to/file1.ts` - [change description]
- `path/to/file2.ts` - [change description]

### Tests Required
- [Test file or coverage note]

**Proceed with these changes?**
```

## Test Enforcement

For every service, controller, or functional code proposed, you MUST also propose corresponding tests.

## Transitions

| Condition | Next State |
|-----------|------------|
| approved | WF_EXECUTE |
| denied | WF_CLARIFY |

## RLVR Signal

- **Type**: permission_gate | **Impact**: neutral

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Permission granted | `WF_EXECUTE` |
| Permission denied | `WF_CLARIFY` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
