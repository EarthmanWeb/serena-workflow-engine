# WF_LOAD_FEATURE - Load Feature Context

> **📂 On step WF_LOAD_FEATURE**

⬆️ OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Execute These Steps

1. **Read relevant domain index:**
   ```
   mcp__serena__read_memory("_INDEX")  # For routing to correct memory
   ```

2. **Read the specific domain/system memory:**
   ```
   # For site-specific work:
   mcp__serena__read_memory("DOM_DISTRICT")   # or DOM_SCHOOLS, DOM_MYSPS, DOM_NETWORK

   # For system-level work:
   mcp__serena__read_memory("SYS_BLOCKS")     # or SYS_CONTEXT_PROVIDERS
   ```

3. **If touching templates, also read:**
   ```
   mcp__serena__read_memory("INDEX_TEMPLATES")
   mcp__serena__read_memory("REF_BLADEONE")
   ```

4. **Note key symbols and file paths** for Serena lookups.

## ⛔ MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| Feature loaded | **Invoke `/arch-review` skill** |

### Skill Invocation for Architecture Review

1. Set workflow context in WORKING_MEMORY:
   - calling_step: WF_LOAD_FEATURE
   - return_step: WF_EXECUTE
2. Invoke `/arch-review` skill
3. The skill will verify approach against architecture patterns
4. Follow the skill's return status to proceed

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

📋 **WORKING_MEMORY:** Update if task state changed (see `REF_WORKING_MEMORY`)

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
