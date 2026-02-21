# WF_UPDATE_MEMORY - Update Memory

> **On step WF_UPDATE_MEMORY**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## When To Use

- Adding/updating domain requirements (`DOM_*`)
- Updating system or reference documentation (`SYS_*`, `REF_*`)
- Creating/updating index files (`INDEX_*`)
- Updating `WM_*` with task progress
- Capturing architectural decisions after WF_ARCH_REVIEW or WF_PLAN_ARCHITECTURE

## Execute These Steps

### 1. Identify Target Memory

| Type      | Naming         | Purpose                                       |
| --------- | -------------- | --------------------------------------------- |
| Domain    | `DOM_[DOMAIN]` | User-facing behavior, constraints, edge cases |
| System    | `SYS_[SYSTEM]` | System documentation                          |
| Reference | `REF_[TOPIC]`  | Reference documentation                       |
| Index     | `INDEX_[TYPE]` | File/symbol indexes                           |
| Working   | `WM_*`         | Session task state                            |

### 2. For WM Updates

**Invoke `/swe-wm-update --from {calling_step}`** — provides the complete
checklist and template. The skill handles reading, validating, and writing WM
comprehensively. Do NOT manually construct WM content or read REF_WM separately.

### 3. For Non-WM Memory Updates

Use Serena tools directly:

```python
mcp__plugin_swe_serena__write_memory("MEMORY_NAME", "content")
mcp__plugin_swe_serena__edit_memory("MEMORY_NAME", "old", "new", "literal")
```

### 4. Confirm to User

"Updated [MEMORY_NAME] with: [brief description]"

---

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition             | MUST Read Next                   |
| --------------------- | -------------------------------- |
| Domain memory updated | `WF_LOAD_FEATURE`                |
| WM updated            | Return to previous workflow step |

1. Read the appropriate WF_* memory NOW
2. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
