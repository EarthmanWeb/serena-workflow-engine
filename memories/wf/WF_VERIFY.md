# WF_VERIFY - Check Work

> **On step WF_VERIFY**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## 1. Re-read CLAUDE_OBLIGATIONS
```
mcp__plugin_swe_serena__read_memory("CLAUDE_OBLIGATIONS")
```
Check for violations:
- [ ] Used inappropriate type assertions (e.g., `as any`)?
- [ ] Created files without permission?
- [ ] Guessed paths without Serena?

## 2. Architecture Check
```
mcp__plugin_swe_serena__read_memory("ARCH_INDEX")
mcp__plugin_swe_serena__read_memory("REF_DEV_STANDARDS")
```
Verify:
- [ ] Components follow documented layer patterns?
- [ ] Functions follow coding standards?
- [ ] Data flow follows architecture documentation?

## 3. Test Coverage Check

**For multi-layer work or user-facing changes:**
- [ ] Functional tests cover the feature?
- [ ] Visual regression tests if UI changed?
- [ ] Tests run and pass?

**Missing tests = GO BACK to WF_EXECUTE and add them.**

## 4. Fix Violations

If any violations found, fix them before proceeding.

## 5. ⚠️ MANDATORY: Update WM

**BEFORE updating, you MUST read:**
```
mcp__plugin_swe_serena__read_memory("REF_WM")
```

**Follow the anti-pattern warnings and multi-section update requirements in REF_WM.**

Include in your update:
- Status: `[COMPLETED]` or `[VERIFY_COMPLETE]`
- Progress: All items marked `[x]`
- Files: All files modified
- Current State: `WF_VERIFY` → `WF_DONE`

**Echo to chat**: `📋 Updated Working Memory: WM_<filename>`

### Also update if needed:
- **DOM_[X]:** If domain architecture changed
- **SYS_[X]:** If system components changed
- **INDEX_[X]:** If indexes need new entries

---

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Violations found | `WF_EXECUTE` (fix them) |
| Tests missing | `WF_EXECUTE` (add them) |
| WM not updated comprehensively | **READ REF_WM, then UPDATE** |
| All clean, tests pass, WM fully updated | `WF_DONE` |

**SKIPPING REF_WM READ = WORKFLOW VIOLATION**
**SINGLE-FIELD STATE EDIT = WORKFLOW VIOLATION**
**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Did you read REF_WM? Did you update comprehensively? Did you report your step?]
