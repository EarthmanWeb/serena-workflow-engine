# WF_UPDATE_MEMORY - Update Memory

> **On step WF_UPDATE_MEMORY**

---

## When To Use

- Adding/updating domain requirements (`DOM_*`)
- Updating system or reference documentation (`SYS_*`, `REF_*`)
- Creating/updating index files (`INDEX_*`)
- Updating `WM_*` with task progress
- Capturing architectural decisions after WF_ARCH_REVIEW

## Before Updating

Always read the target memory before modifying it:

```
read_memory("[memory_name]")
```

This prevents data loss and ensures targeted edits rather than blind overwrites.

Use `list_memories()` or `INDEX_FEATURES` to find the correct memory name.

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

Invoke `/swe-wm-update --from {calling_step}` — provides the complete checklist and template. The skill handles reading, validating, and writing WM comprehensively.

### 3. For Non-WM Memory Updates

Use Serena tools directly:

```python
mcp__plugin_swe_serena__write_memory("MEMORY_NAME", "content")
mcp__plugin_swe_serena__edit_memory("MEMORY_NAME", "old", "new", "literal")
```

### 4. Confirm to User

"Updated [MEMORY_NAME] with: [brief description]"

---

## Routing

| Condition             | Next Step                        |
| --------------------- | -------------------------------- |
| Domain memory updated | `WF_CLASSIFY`                    |
| WM updated            | Return to previous workflow step |

Update WM via `/swe-wm-update` before transitioning.
