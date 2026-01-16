# WF_DONE - Task Complete

> **On step WF_DONE**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## ⚠️ FINAL WORKING_MEMORY UPDATE - MANDATORY

**Before completing, you MUST update WORKING_MEMORY with final status.**

```
mcp__serena__write_memory("WORKING_MEMORY_<timestamp>_<descriptor>", "<content>")
```

Include:
- Final status: Completed
- Summary of what was done
- Any follow-up items for next conversation
- Memories updated during session

**Echo to chat**: `Working Memory: WORKING_MEMORY_<filename>`

---

## Checklist Before Finishing

- [ ] **WORKING_MEMORY updated with final status** (REQUIRED)
- [ ] Feature memories updated if needed (DOM_*, SYS_*, INDEX_*)
- [ ] No pending violations
- [ ] User informed of any follow-up items

---

## Summarize To User

- What was done
- Any memories updated
- Any follow-up items (documented in WORKING_MEMORY)

**DO NOT mark task complete without updating WORKING_MEMORY.**

[CRITICAL: Did you update WORKING_MEMORY? Are you on a WF_* workflow step? Did you report on it?]
