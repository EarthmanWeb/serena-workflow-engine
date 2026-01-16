# WF_LOAD_FEATURE

> **📦 On step WF_LOAD_FEATURE**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Load feature context from memories before implementation.

## Entry

- **From**: WF_DETECT_REQ, WF_REQUIREMENT, WF_UPDATE_MEMORY
- **Triggers**: requirements_confirmed

## Required Actions

1. `read_feature_memory` - Load FEATURE_[KEY] from WORKING_MEMORY
2. `read_domain_memories` - Load relevant DOM_* memories
3. `read_system_memories` - Load relevant SYS_* memories
4. `build_context` - Assemble implementation context

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: never

## Memory Loading Pattern

```
1. Get feature key from WORKING_MEMORY
2. Read FEATURE_[KEY] for architecture info
3. Read DOM_* for domain patterns
4. Read SYS_* for system conventions
5. Read REF_* for codebase-wide standards
```

## Transitions

| Condition | Next State |
|-----------|------------|
| loaded | WF_ARCH_REVIEW |

## RLVR Signal

- **Type**: feature_load | **Impact**: neutral

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Feature loaded | `WF_ARCH_REVIEW` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
