# WF_CHECKPOINT - Update Progress

> **On step WF_CHECKPOINT**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## ⚠️ CRITICAL: UPDATE WM NOW

**This step exists specifically to update WM. You MUST do this.**

**MANDATORY: Read REF_WM BEFORE updating:**
```
mcp__plugin_swe_serena__read_memory("REF_WM")
```

Then update:
```
mcp__plugin_swe_serena__write_memory("WM_<timestamp>_<descriptor>", "<content>")
```

**⛔ NEVER do single-field state edits. Follow anti-pattern warnings in REF_WM.**

**Format** (see `REF_WM` for full details):
```markdown
# WM - [Date] [Descriptor]

## Session Context
- **Task**: [Brief description]
- **Feature**: [Feature key from INDEX_FEATURES]
- **Status**: In Progress / Completed / Blocked

## Progress Tracking
- ✅ Completed items
- 🔄 Current item
- ⏳ Pending items

## Notes
[Any blockers, decisions, findings]

## Last Updated
[Timestamp]
```

**Echo to chat**: `Working Memory: WM_<filename>`

---

## Triggers for this state
- Created/deleted a file
- Modified multiple symbols
- Completed a phase
- ~5 minutes elapsed since last update

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| More work remains | `WF_EXECUTE` |
| All work complete | `WF_VERIFY` |

1. **VERIFY** you updated WM
2. Determine which condition applies
3. Read that WF_* memory NOW
4. Report the new step to user

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**
**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Did you update WM? Are you on a WF_* workflow step? Did you report on it?]
