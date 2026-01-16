# WF_CONTINUE - Resume Previous Work

> **On step WF_CONTINUE**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Execute These Steps

1. **VERIFY WORKING_MEMORY exists** (should have been created at WF_START)
   - If missing: **STOP** - go back and create it per `REF_WORKING_MEMORY`
   - Echo to chat: `Working Memory: WORKING_MEMORY_<timestamp>_<descriptor>`

2. **Check current task state:**
   - What was in progress?
   - Any blockers noted?
   - What's the next step?

3. **Determine resume point** (see table below)

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| Was executing (multi-layer: >1 architectural layer) | `WF_ARCH_REVIEW` |
| Was executing (single-layer) | `WF_EXECUTE` |
| Was blocked/unclear | `WF_CLARIFY` |
| No previous state | `WF_CLASSIFY` |

**Multi-layer detection:** Check WORKING_MEMORY "Layers:" field or infer from files being modified. Layers are defined in FEATURE_[KEY] and ARCH_INDEX.

1. Determine which condition applies
2. Read that WF_* memory NOW
3. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
