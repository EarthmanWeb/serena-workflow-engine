# WF_DETECT_REQ - Requirement Detection

> **🔍 On step WF_DETECT_REQ**

⬆️ OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Scan User Message For

- "should", "must", "needs to", "has to"
- "users want", "behavior should be"
- "always do X", "never do Y"
- Corrections to current behavior
- UX preferences or constraints

## Decision

**Requirement found?**
- Yes → contains behavioral/UX requirement
- No → pure implementation task

## ⛔ MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| Requirement found | `WF_REQUIREMENT` |
| No requirement | `WF_LOAD_FEATURE` |

1. Determine which condition applies
2. Read that WF_* memory NOW
3. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

## ⚠️ MANDATORY: WORKING_MEMORY UPDATE

**Before transitioning to another state, you MUST:**
1. Update `## Progress` with detected requirements
2. Update `**Files:**` with files examined
3. Verify `## Workflow Context` is current

**SKIPPING WORKING_MEMORY UPDATE = WORKFLOW VIOLATION**

The hooks will BLOCK your next action if WORKING_MEMORY is stale.

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
