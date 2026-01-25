# WF_LOAD_FEATURE - Load Feature Context

> **📂 On step WF_LOAD_FEATURE**

⬆️ OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Execute These Steps

1. **Read the feature index to discover available features:**
   ```
   mcp__plugin_swe_serena__read_memory("INDEX_FEATURES")
   ```

2. **From INDEX_FEATURES, identify and read relevant memories:**
   - Look for `DOM_*` entries for domain-specific context
   - Look for `SYS_*` entries for system-level components
   - Look for `REF_*` entries for reference documentation
   - Look for `INDEX_*` entries for additional indexes

3. **Read the specific memories identified:**
   ```
   # Example - read whatever domains/systems are relevant to your task:
   mcp__plugin_swe_serena__read_memory("DOM_[DOMAIN]")
   mcp__plugin_swe_serena__read_memory("SYS_[SYSTEM]")
   mcp__plugin_swe_serena__read_memory("REF_[TOPIC]")
   ```

4. **Note key symbols and file paths** for Serena lookups.

## ⛔ MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| Feature loaded | **Invoke `/arch-review` skill** |

### Skill Invocation for Architecture Review

1. Set workflow context in WM:
   - calling_step: WF_LOAD_FEATURE
   - return_step: WF_EXECUTE
2. Invoke `/arch-review` skill
3. The skill will verify approach against architecture patterns
4. Follow the skill's return status to proceed

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

📋 **WM:** Update if task state changed (see `REF_WM`)

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
