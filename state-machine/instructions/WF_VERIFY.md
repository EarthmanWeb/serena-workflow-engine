# WF_VERIFY - Check Work

> **On step WF_VERIFY**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Execute These Steps

### 1. Re-read CLAUDE_OBLIGATIONS
```
mcp__serena__read_memory("CLAUDE_OBLIGATIONS")
```
Check behavioral violations:
- [ ] Used inappropriate type assertions (e.g., `as any`)?
- [ ] Created files without permission?
- [ ] Guessed paths without Serena?

### 2. Architecture Check
```
mcp__serena__read_memory("ARCH_INDEX")
mcp__serena__read_memory("REF_DEV_STANDARDS")
```
Verify patterns (based on feature's ARCH_INDEX):
- [ ] Components follow documented layer patterns?
- [ ] Functions follow coding standards (see `REF_DEV_STANDARDS`)?
- [ ] Data flow follows architecture documentation?

### 3. Test Coverage Check

**For multi-layer work or user-facing changes:**
- [ ] Functional tests cover the feature? (see `REF_TESTING`)
- [ ] Visual regression tests if UI changed?
- [ ] Tests run and pass?

Run tests using commands from FEATURE_[KEY] or REF_DEV_STANDARDS:
```bash
# Example - customize per project
[test-command] -- --grep "feature-name"
```

**If tests are missing for user-facing features, this is a violation.**

**Missing tests = GO BACK to WF_EXECUTE and add them before proceeding.**

### 4. Fix Violations

If any violations found, fix them before proceeding.

### 5. ⚠️ MANDATORY: Update Memories

**You MUST update WORKING_MEMORY before proceeding to WF_DONE.**

```
mcp__serena__write_memory("WORKING_MEMORY_<timestamp>_<descriptor>", "<content>")
```

Include:
- Status: Verify Complete / Ready for Done
- Work completed
- Tests passed/skipped
- Any memories updated

**Echo to chat**: `Working Memory: WORKING_MEMORY_<filename>`

Also update if needed:
- **DOM_[X]:** Update if domain architecture changed
- **SYS_[X]:** Update if system components changed
- **INDEX_[X]:** Update if indexes need new entries

---

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| Violations found | `WF_EXECUTE` (fix them) |
| Tests missing | `WF_EXECUTE` (add them) |
| WORKING_MEMORY not updated | **UPDATE IT NOW** |
| All clean, tests pass, WORKING_MEMORY updated | `WF_DONE` |

1. Determine which condition applies
2. **VERIFY WORKING_MEMORY is updated**
3. Read that WF_* memory NOW
4. Report the new step to user

**SKIPPING WORKING_MEMORY UPDATE = WORKFLOW VIOLATION**
**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Did you update WORKING_MEMORY? Are you on a WF_* workflow step? Did you report on it?]
