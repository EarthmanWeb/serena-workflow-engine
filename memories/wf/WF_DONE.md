# WF_DONE - Task Complete

> **On step WF_DONE**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## ⚠️ FINAL WM UPDATE - MANDATORY

**Before completing, you MUST update WM with final status.**

```
mcp__plugin_swe_serena__write_memory("WM_<timestamp>_<descriptor>", "<content>")
```

Include:
- Final status: Completed
- Summary of what was done
- Any follow-up items for next conversation
- Memories updated during session

**Echo to chat**: `Working Memory: WM_<filename>`

---

## Checklist Before Finishing

- [ ] **WM updated with final status** (REQUIRED)
- [ ] Feature memories updated if needed (DOM_*, SYS_*, INDEX_*)
- [ ] No pending violations
- [ ] User informed of any follow-up items

---

## Summarize To User

- What was done
- Any memories updated
- Any follow-up items (documented in WM)

**DO NOT mark task complete without updating WM.**

---

## 🔄 Same-Session New Task Handling

**When a new task arrives AFTER completing WF_DONE in the same session:**

This session's WM should be PRESERVED and UPDATED, not replaced.

### What to Do:

1. **Keep the existing WM file** - do NOT create a new one
2. **Update the WM with the new task:**
   - Increment `Task Iteration` counter (e.g., `Task Iteration: 2`)
   - Add new task to `## Active Task` section
   - Preserve `## Completed Tasks` history from previous iterations
   - Reset `Edit Count Since Checkpoint` to 0
   - Update `Current State` to the appropriate next step (typically `WF_CLASSIFY`)

3. **Transition to WF_CLASSIFY** for the new task:
   ```
   mcp__plugin_swe_serena__read_memory("WF_CLASSIFY")
   ```

### WM Update Template for New Task:

```markdown
## Workflow Context
- **Current State**: WF_CLASSIFY
- **Task Iteration**: [INCREMENT PREVIOUS VALUE]
- **Edit Count Since Checkpoint:** 0

## Active Task
[NEW TASK DESCRIPTION]

## Completed Tasks (This Session)
### Iteration 1: [Previous Task Title]
- Status: ✅ Completed
- Summary: [What was done]
```

**The session ID in the WM filename remains the same - only the content is updated.**

[CRITICAL: Did you update WM? Are you on a WF_* workflow step? Did you report on it?]
