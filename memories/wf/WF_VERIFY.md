# WF_VERIFY - Check Work

> **On step WF_VERIFY**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## 1. Re-read CLAUDE_OBLIGATIONS

```
mcp__plugin_swe_serena__read_memory("claude/CLAUDE_OBLIGATIONS")
```

Check for violations:

- [ ] Used inappropriate type assertions (e.g., `as any`)?
- [ ] Created files without permission?
- [ ] Guessed paths without Serena?

## 2. Architecture & Compliance Check

```
mcp__plugin_swe_serena__read_memory("arch/ARCH_INDEX")
mcp__plugin_swe_serena__read_memory("feature/FEATURE_DEV_STANDARDS")
```

### 2a. Generic Layer Verification

- [ ] Components follow documented layer patterns?
- [ ] Functions follow coding standards?
- [ ] Data flow follows architecture documentation?

### 2b. Project Compliance Checklist Verification

**Read the `## Compliance Checklist` from WM** (written at WF_ARCH_REVIEW Step 2c).

**For EACH item in the checklist:**

- [ ] Verify it was satisfied in the implementation
- [ ] If violated, note what needs fixing

**If no compliance checklist exists in WM** (e.g., task skipped WF_ARCH_REVIEW): use the generic checks in 2a only.

### 2c. Integration Completeness Check

**For any NEW files or components created, verify they are wired in:**

- [ ] New scripts/styles enqueued in the asset loader?
- [ ] New handlers/modules registered in the registration system?
- [ ] New templates/blocks discoverable by the template engine?
- [ ] New PHP classes instantiated or autoloaded?
- [ ] New routes/endpoints registered with the framework?

**Check FEATURE_[KEY] for the feature's specific integration points.** Not all of the above apply to every project — use the ones relevant to your feature.

**Integration completeness failures are silent** — code works in isolation but is never loaded. This is the most common post-implementation defect.

## 3. Test Coverage Check

### 3a. Tests-as-Deliverable Verification

**If the task deliverable IS tests (writing new tests, fixing tests, adding test coverage):**

The tests themselves are NOT the verification. Verification means confirming the tests work correctly:

- [ ] Run the new/modified tests — they must execute without runtime errors
- [ ] Tests pass when they should pass (happy path assertions hold)
- [ ] Tests fail when they should fail (if feasible: temporarily break the feature under test → confirm the test catches it)
- [ ] No false positives (tests don't pass trivially or vacuously)

**Failing to run the tests = unverified deliverable. GO BACK to WF_EXECUTE.**

After confirming test behavior, skip to Section 4 (no browser verification needed for test-only deliverables).

---

### 3b. Standard Test Coverage (Non-Test Deliverables)

**For multi-layer work or user-facing changes:**

- [ ] Functional tests cover the feature?
- [ ] Visual regression tests if UI changed?
- [ ] Tests run and pass?

**If automated tests exist:** Run them. Failing tests = GO BACK to WF_EXECUTE and fix them.

### 3c. Browser Verification Fallback (No Automated Tests)

**If NO automated tests exist for this feature**, you MUST verify the work visually in the dev browser when a local environment is available.

#### Prerequisites

1. **Check for local environment** — look for local dev server URLs in FEATURE_[KEY], project config, or `.serena/` files. If no local environment is available, note it in WM and skip to Step 4.
2. **Check for saved scenarios** — call `mcp__browser-devtools__scenario-list()` FIRST.

#### Verification Steps

| Step | Action |
|------|--------|
| 1 | **Use scenarios first** — if a saved scenario covers the flow you changed, run it with `scenario-run`. Scenarios are more reliable than manual step-by-step interaction. |
| 2 | **Manual verification** — if no scenario matches, navigate to the affected page(s), take an ARIA snapshot, and verify the changes are reflected in the UI. |
| 3 | **Screenshot evidence** — take a screenshot of the verified state for WM documentation. |
| 4 | **Create scenario** — if you performed manual steps that would be useful for future verification, save them as a new scenario with `scenario-add`. |

**⚠️ CRITICAL: Follow browser devtools rules:**
- ARIA snapshot FIRST for structure — NOT screenshots
- NEVER guess selectors — always snapshot before interacting
- Use `scenario-run` over individual tool calls whenever possible

**If no local environment AND no automated tests:** Note in WM that verification was not possible and flag for user attention before proceeding to WF_DONE.

## 4. Fix Violations

If any violations found, fix them before proceeding.

## 5. ⚠️ MANDATORY: Update WM

**Invoke `/swe-wm-update --from WF_VERIFY`** — provides the complete checklist
and template. The skill handles reading, validating, and writing WM
comprehensively. Do NOT manually construct WM content or read REF_WM separately.

### Also update if needed:

- **DOM_[X]:** If domain architecture changed
- **SYS_[X]:** If system components changed
- **INDEX_[X]:** If indexes need new entries

---

## MANDATORY NEXT STEP

| Condition                               | MUST Read Next                               |
| --------------------------------------- | -------------------------------------------- |
| Violations found                                     | `WF_EXECUTE` (fix them)                      |
| Tests missing AND no browser verification possible   | `WF_EXECUTE` (add tests)                     |
| Browser verification failed (visual defects found)   | `WF_EXECUTE` (fix them)                      |
| WM not updated comprehensively                       | **Invoke `/swe-wm-update --from WF_VERIFY`** |
| All clean, tests/browser verification pass, WM updated | `WF_DONE`                                  |

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**
**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Did you invoke `/swe-wm-update`? Did you update comprehensively? Did you report your step?]
