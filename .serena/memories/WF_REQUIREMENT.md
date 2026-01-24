# WF_REQUIREMENT - Handle Requirement

> **On step WF_REQUIREMENT**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Execute These Steps

1. **Check for existing domain memory:**
   ```
   mcp__serena__list_memories()
   ```
   Look for DOM_* memories that relate to this requirement.

2. **Read the relevant domain memory if it exists:**
   ```
   mcp__serena__read_memory("DOM_[DOMAIN]")
   ```
   If memory doesn't exist, you may need to create it.

3. **Compare user's requirement to memory:**
   - NEW: Add requirement
   - CONFLICT: Ask before updating
   - EXISTS: Acknowledge and proceed

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| New requirement to add | `WF_UPDATE_MEMORY` |
| Requirement conflicts | `WF_CLARIFY` |
| Requirement exists | `WF_LOAD_FEATURE` |

1. Determine which condition applies
2. Read that WF_* memory NOW
3. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

📋 **WORKING_MEMORY:** Update if task state changed (see `REF_WORKING_MEMORY`)

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
