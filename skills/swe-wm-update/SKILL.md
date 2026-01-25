---
name: swe-wm-update
version: 1.0.0
description: Single-operation Working Memory update with validation
workflow:
  aware: true
  callable_from:
    - WF_START
    - WF_CLASSIFY
    - WF_EXECUTE
    - WF_CHECKPOINT
    - WF_VERIFY
    - WF_DONE
  default_return: null
  supports_standalone: false
  auto_transition: false
args:
  - name: session_id
    description: 8-char session ID (required)
    required: true
  - name: task
    description: Task description (required)
    required: true
  - name: feature
    description: Feature key(s) from INDEX_FEATURES (required)
    required: true
  - name: state
    description: Current workflow state WF_* (required)
    required: true
  - name: progress
    description: Progress items as markdown list (required)
    required: true
  - name: complexity
    description: simple|medium|large (optional, default medium)
    required: false
---

## ⚠️ WORKFLOW INITIALIZATION

**If starting a new session**, first read workflow initialization:
```
mcp__plugin_swe_serena__read_memory("WF_INIT")
```
Follow WF_INIT instructions before executing this skill.

---

# /swe-wm-update

**CRITICAL: This is the ONLY way to update Working Memory.**

Do NOT use multiple `edit_memory` calls. Each call triggers the daemon.
Use this skill to make ONE complete write.

## Anti-Pattern (DO NOT DO THIS)

```python
# WRONG - 4 daemon calls!
edit_memory("WM_...", "Task: old", "Task: new", "literal")
edit_memory("WM_...", "Feature: old", "Feature: new", "literal")
edit_memory("WM_...", "State: old", "State: new", "literal")
edit_memory("WM_...", "Progress: old", "Progress: new", "literal")
```

## Correct Pattern

```
/swe-wm-update session_id=a7380848 task="Fix bug in auth" feature=BACKEND state=WF_EXECUTE progress="- [x] Identified issue\n- [ ] Implement fix"
```

## Required Data

Before invoking, you MUST have ALL of:

| Field | Source | Example |
|-------|--------|---------|
| session_id | From hook output or WM filename | `a7380848` |
| task | User's request summary | `"Refactor auth module"` |
| feature | INDEX_FEATURES key | `BACKEND` or `BLOCKS,THEMES` |
| state | Current WF_* step | `WF_EXECUTE` |
| progress | Markdown checklist | `"- [x] Step 1\n- [ ] Step 2"` |

## Process

### Step 1: Validate Required Fields

If ANY field is missing, STOP and gather it first:
- No session_id? → Check hook output or `mcp__plugin_swe_serena__list_memories()`
- No task? → Ask user or infer from conversation
- No feature? → Check `INDEX_FEATURES` or ask user
- No state? → Determine from workflow position
- No progress? → Create initial checklist from task

### Step 2: Build Complete WM Content

```markdown
# Working Memory: Session {session_id}

## Session
- **ID**: {session_id}
- **Task**: {task}
- **Started**: {timestamp}

## Workflow Context
**Current State**: {state}
**Previous State**: {previous_state or 'None'}

## Task Context
- **Feature(s)**: {feature}
- **Complexity**: {complexity}

## Progress Tracking
### Pending
{progress}

## Requirements
{requirements or '(from user request)'}

## Implementation Notes
{notes or '(none yet)'}
```

### Step 3: Single Write Operation

```python
mcp__plugin_swe_serena__write_memory("WM_{session_id}_session", content)
```

**ONE call. Not multiple edits.**

### Step 4: Confirm

Output: `📋 Updated Working Memory: WM_{session_id}_session`

## State Transitions

When updating state, also update progress:

| From → To | Progress Update |
|-----------|-----------------|
| WF_START → WF_CLASSIFY | Add classification checklist |
| WF_CLASSIFY → WF_EXECUTE | Add implementation checklist |
| WF_EXECUTE → WF_VERIFY | Mark implementation done, add verify checklist |
| WF_VERIFY → WF_DONE | Mark all complete |

## Validation Rules

The skill will FAIL if:
1. session_id doesn't match `[a-f0-9]{8}` pattern
2. state doesn't match `WF_*` pattern
3. feature is empty or "(to be determined)"
4. task is empty or "(awaiting user task)"
5. progress has no items

## Exit

No explicit exit - this is a utility skill that returns to caller.
