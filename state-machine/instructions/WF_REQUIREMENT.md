# WF_REQUIREMENT

> **📝 On step WF_REQUIREMENT**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Document and confirm requirements with user.

## Entry

- **From**: WF_DETECT_REQ
- **Triggers**: requirements_detected

## Required Actions

1. `format_requirements` - Present requirements clearly
2. `confirm_with_user` - Get explicit confirmation
3. `update_working_memory` - Store confirmed requirements

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: never

## Requirement Confirmation Format

```markdown
## Detected Requirements

### Explicit
- [What user asked for]

### Implicit
- [Inferred needs]

### Edge Cases
- [Error handling, validation]

**Please confirm these requirements are correct.**
```

## Transitions

| Condition | Next State |
|-----------|------------|
| confirmed | WF_LOAD_FEATURE |
| needs_clarification | WF_CLARIFY |
| update_memory | WF_UPDATE_MEMORY |

## RLVR Signal

- **Type**: requirement_doc | **Impact**: neutral

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| User confirmed | `WF_LOAD_FEATURE` |
| Needs clarification | `WF_CLARIFY` |
| Memory update needed | `WF_UPDATE_MEMORY` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
