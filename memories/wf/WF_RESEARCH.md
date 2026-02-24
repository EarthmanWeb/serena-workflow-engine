# WF_RESEARCH - Research Only

> **🔬 On step WF_RESEARCH**

⬆️ OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## For Questions/Exploration Without Code Changes

1. **Use Serena tools to explore:**
   - `mcp__plugin_swe_serena__find_symbol`
   - `mcp__plugin_swe_serena__get_symbols_overview`
   - `mcp__plugin_swe_serena__search_for_pattern`

2. **Read relevant memories if needed.**

3. **Report findings to user.**

## Rules

- NO code changes in this path
- NO file creation
- Information gathering only

## ⛔ MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** After reporting findings:

| Condition                             | MUST Read Next    |
| ------------------------------------- | ----------------- |
| Research complete, user wants changes | `WF_LOAD_FEATURE` |
| Research complete, no changes needed  | `WF_DONE`         |

If the user wants to proceed with implementation based on research findings, route to `WF_LOAD_FEATURE` to load feature context before any code changes.

If research answered the user's question with no further action needed, route to `WF_DONE`.

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

## ⚠️ MANDATORY: WM UPDATE

**Before transitioning, invoke `/swe-wm-update --from WF_RESEARCH`** — provides the
step-specific checklist ensuring no fields are missed. Do NOT manually update WM
without it.

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
