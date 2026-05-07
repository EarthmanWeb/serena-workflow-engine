## ⛔ MANDATORY ENTRY POINT — FIRST MESSAGE ONLY ⛔

**On the FIRST message of a conversation (no Working Memory exists yet), your FIRST tool call MUST be:**

```
mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_INIT")
```

**Then follow WF_INIT instructions completely (read WF_START, create Working Memory, classify task).**

### When this applies:

- **First message only** — no WM file exists for this session yet.
- If hooks block you for missing Working Memory, that means you skipped this step. Fix it immediately.

### When this does NOT apply:

- **Subsequent messages in the same session** — the prompt hook (`swe_user_prompt_workflow.py`) handles state routing. Follow its instructions instead.
- If the prompt hook says "continue workflow" or routes you to a specific WF\_\* state, go there directly. Do NOT re-read WF_INIT.

### ⚠️ TRAP: Pre-loaded context from system-reminder, ide_selection, or ide_opened_file

- If you see file contents already loaded in system-reminder tags, **IGNORE THEM until after WF_INIT is complete** (first message only).
- Pre-loaded context is NOT a substitute for the initialization workflow on first message.

### CRITICAL: Mandatory Hook Actions

Hooks will send you data to guide you. ALWAYS LISTEN TO THEM.

- Did you follow hook instructions exactly?
- Did you read all references mentioned in hook responses COMPLETELY?
- Did you use Serena tools before Read/Edit?
- Did you check the codebase for existing patterns before creating new ones?
