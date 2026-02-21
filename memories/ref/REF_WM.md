# REF_WM

## Naming

`WM_<SESSION_ID>.md`

- **Session ID**: 8-char from transcript_path UUID (e.g., `3fe6b3c5`)

## Lifecycle

| Stage           | When                    | What Happens                                                       |
| --------------- | ----------------------- | ------------------------------------------------------------------ |
| **Auto-Create** | WF_START transition     | Hook creates `WM_{session_id}.md`                                  |
| **Load**        | Session resume          | Read file → verify session ID matches → echo to chat               |
| **Update**      | After edits/transitions | Write changes → echo: `📋 Updated Working Memory: WM_{session_id}` |

**The WM filename is always `WM_{session_id}` — no suffix, no renaming.**

**Update is MANDATORY after:** memory edits, file edits, workflow transitions, state changes.

---

## ⛔ ANTI-PATTERNS

### ❌ Multiple edit_memory Calls

**THIS IS WRONG - DO NOT DO THIS:**

```python
# ❌ WRONG: Multiple daemon calls!
edit_memory("WM_...", "Task: old", "Task: new", "literal")
edit_memory("WM_...", "Feature: old", "Feature: new", "literal")
edit_memory("WM_...", "State: old", "State: new", "literal")
```

**Why it's wrong:** Each `edit_memory` call triggers the daemon. 4 edits = 4 daemon calls = inefficient.

### ❌ State-Only Edits

```python
# ❌ WRONG: Only changing Current State field
edit_memory("WM_...", "Current State: WF_EXECUTE", "Current State: WF_VERIFY", "literal")
```

**Why it's wrong:** Captures no progress, no completed work, no context.

---

## ✅ CORRECT: Single write_memory Call

**Use ONE `write_memory` call with complete content:**

```python
# ✅ CORRECT: Single write with all sections
mcp__plugin_swe_serena__write_memory("WM_{session}", """
# Working Memory: Session {session}

## Session
- **ID**: {session}
- **Task**: {complete task description}
...full content...
""")
```

### Required Sections for ANY Update:

| Section         | What to Update                              |
| --------------- | ------------------------------------------- |
| `Current State` | New workflow state                          |
| `Task`          | Current task description                    |
| `Feature(s)`    | Active feature keys                         |
| `Progress`      | Updated checklist with `[x]` for done items |

**ONE WRITE CALL = ONE DAEMON CALL = CORRECT**

---

## Template

```markdown
# Working Memory

## Chat: <descriptor>

Session: <SESSION_ID>

## Workflow Context

- **Calling Step**: WF_CLASSIFY
- **Feature Key(s)**: BLOCKS
- **Session ID**: 3fe6b3c5
- **Return Step**: WF_DETECT_REQ
- **Invocation Mode**: workflow
- **Current State**: WF_EXECUTE
- **Task Iteration**: 1
- **Edit Count Since Checkpoint:** 0

## Current Task

**[STATUS]**: [Task Name]

### Context

[1-2 sentences]

### Feature(s)

[Single feature key OR comma-separated list]

### Progress

- [ ] Step 1
- [x] Step 2

**Files:** `path/to/file.php` - [note]

## Previous Task

**[OUTCOME]**: [Task name] - [summary]

## Completed Tasks (This Session)

<!-- Used when multiple tasks are completed in same session -->

### Iteration 1: [Task Title]

- Status: ✅ Completed
- Summary: [What was done]
- Files Modified: [list]
```

---

## Workflow Context (REQUIRED for Stop Hook)

| Field                         | Purpose                                                    |
| ----------------------------- | ---------------------------------------------------------- |
| `Calling Step`                | Which WF_* invoked current action                          |
| `Current State`               | **CRITICAL** - Active state (used by stop hook)            |
| `Feature Key(s)`              | Active feature(s) from INDEX_FEATURES                      |
| `Session ID`                  | 8-char unique ID                                           |
| `Return Step`                 | Where to return after completion                           |
| `Invocation Mode`             | `workflow` \| `standalone` \| `swarm_agent`                |
| `Task Iteration`              | Counter for tasks in same session (starts at 1)            |
| `Edit Count Since Checkpoint` | Edits since last working memory update (reset on new task) |

**Stop Hook Behavior:**

| State                                     | Behavior                    |
| ----------------------------------------- | --------------------------- |
| `WF_DONE`, `WF_CLEANUP`                   | Clean exit                  |
| `WF_EXECUTE`, `WF_DEBUG_TDD`, `WF_VERIFY` | ⚠️ Warning: incomplete work |

---

## Skill Return Section (Optional)

```markdown
## Skill Return

- **Skill**: research
- **Status**: success_with_findings
- **Findings Summary**: [brief]
- **Artifacts**: [list]
- **Next Step Hint**: WF_DETECT_REQ
```

**Status codes:** `success`, `success_with_findings`, `needs_clarification`, `blocked`, `escalate_complexity`

---

## Rules

1. One file per conversation
2. Echo ID on every operation
3. Verify session ID on load
4. Update after significant actions
5. **NEVER do single-field state edits**
6. **WM filename is always `WM_{session_id}` — never add suffixes or rename**
