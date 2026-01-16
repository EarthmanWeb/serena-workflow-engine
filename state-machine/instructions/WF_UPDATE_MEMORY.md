# WF_UPDATE_MEMORY - Update Memory

> **On step WF_UPDATE_MEMORY**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## When To Use

- Adding new requirement to domain memory
- Updating existing requirement after clarification
- Creating new domain memory that doesn't exist
- Updating WORKING_MEMORY with task progress
- **Capturing architectural decisions after WF_ARCH_REVIEW or WF_PLAN_ARCHITECTURE**

## Execute These Steps

IMPORTANT: ONLY WRITE THE MEMORY FOR THIS TASK

1. **Identify the target memory:**
   - Domain requirement -> `DOM_[DOMAIN]`
   - System documentation -> `SYS_[SYSTEM]`
   - Reference documentation -> `REF_[TOPIC]`
   - Index -> `INDEX_[TYPE]`
   - Working state -> `WORKING_MEMORY_<conversation_id>`

2. **For DOM_* memories, include:**
   - User-facing behavior description
   - Any constraints or edge cases
   - Related files/symbols if known

3. **For WORKING_MEMORY:**
   - Filename: `WORKING_MEMORY_<conversation_id>` (use your conversation ID)
   - See `REF_WORKING_MEMORY` for format template and rules
   - Each conversation has its own isolated file

4. **For architecture snapshots (after reading SYS_* or REF_* memories), include:**
   - Which layers are involved
   - Which SYS_* and REF_* were consulted
   - Key constraints that apply to this task
   - This enables proper resume after session breaks

5. **Use Serena to update:**
   ```
   mcp__serena__write_memory("DOM_[DOMAIN]", "content")
   mcp__serena__edit_memory("DOM_[DOMAIN]", "old", "new", "literal")
   ```

6. **Confirm to user:**
   "Updated [MEMORY_NAME] with: [brief description]"

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| Domain memory updated | `WF_LOAD_FEATURE` |
| WORKING_MEMORY updated | Return to previous workflow step |

1. Read the appropriate WF_* memory NOW
2. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
