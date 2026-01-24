# REF_WM

## Naming

`WM_<SESSION_ID>_<descriptor>.md`

- **Session ID**: 8-char from transcript_path UUID (e.g., `3fe6b3c5`)
- **Descriptor**: 2-4 words, snake_case (e.g., `theme_refactor`)

## Create / Load / Update

| Action | Steps |
|--------|-------|
| **Create** | Get session ID from hook → pick descriptor → write file → echo to chat |
| **Load** | Read file → verify session ID matches → echo to chat |
| **Update** | Write changes → echo to chat: `📋 Updated Working Memory: WM_<filename>` |

**Update is MANDATORY after:** memory edits, file edits, workflow transitions, state changes.

---

## ⛔ ANTI-PATTERN: State-Only Edits

**THIS IS WRONG - DO NOT DO THIS:**
```python
# ❌ WRONG: Only changing Current State field
edit_memory("WM_...", "Current State: WF_EXECUTE", "Current State: WF_VERIFY", "literal")
```

**Why it's wrong:** Captures no progress, no completed work, no context. Memory becomes useless for resumption.

### ✅ A VALID Update MUST Modify MULTIPLE Sections:

| Section | What to Update |
|---------|----------------|
| `Current State` | New workflow state |
| `Status` | `[IN PROGRESS]` → `[COMPLETED]` |
| `Progress` | Mark completed items with `[x]` |
| `Files` | Add any new files modified |
| `Context` | Add findings, blockers, decisions |

**Correct approach:**
```python
# ✅ CORRECT: Full rewrite with all sections
write_memory("WM_...", "<full updated content>")

# ✅ ALSO CORRECT: Multiple targeted edits
edit_memory(..., "- [ ] Step 3", "- [x] Step 3", "literal")
edit_memory(..., "[IN PROGRESS]", "[COMPLETED]", "literal")
edit_memory(..., "Current State: WF_EXECUTE", "Current State: WF_VERIFY", "literal")
```

**SINGLE-FIELD STATE EDIT = WORKFLOW VIOLATION**

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

| Field | Purpose |
|-------|---------|
| `Calling Step` | Which WF_* invoked current action |
| `Current State` | **CRITICAL** - Active state (used by stop hook) |
| `Feature Key(s)` | Active feature(s) from INDEX_FEATURES |
| `Session ID` | 8-char unique ID |
| `Return Step` | Where to return after completion |
| `Invocation Mode` | `workflow` \| `standalone` \| `swarm_agent` |
| `Task Iteration` | Counter for tasks in same session (starts at 1) |
| `Edit Count Since Checkpoint` | Edits since last working memory update (reset on new task) |

**Stop Hook Behavior:**

| State | Behavior |
|-------|----------|
| `WF_DONE`, `WF_CLEANUP` | Clean exit |
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
