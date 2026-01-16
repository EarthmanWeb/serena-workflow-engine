# WF_CHECKPOINT - Update Progress

> **On step WF_CHECKPOINT**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## ⚠️ CRITICAL: UPDATE WORKING_MEMORY NOW

**This step exists specifically to update WORKING_MEMORY. You MUST do this.**

```
mcp__serena__write_memory("WORKING_MEMORY_<timestamp>_<descriptor>", "<content>")
```

**Format** (see `REF_WORKING_MEMORY` for full details):
```markdown
# WORKING_MEMORY - [Date] [Descriptor]

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

**Echo to chat**: `Working Memory: WORKING_MEMORY_<filename>`

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

1. **VERIFY** you updated WORKING_MEMORY
2. Determine which condition applies
3. Read that WF_* memory NOW
4. Report the new step to user

**SKIPPING WORKING_MEMORY UPDATE = WORKFLOW VIOLATION**
**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Did you update WORKING_MEMORY? Are you on a WF_* workflow step? Did you report on it?]
