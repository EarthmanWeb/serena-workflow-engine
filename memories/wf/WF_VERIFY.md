# WF_VERIFY - Check Work

> **On step WF_VERIFY**

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

### 2b. Compliance Checklist Verification

Read the `## Compliance Checklist` from WM (written at WF_ARCH_REVIEW Step 2c).

For each item in the checklist:

- [ ] Verify it was satisfied in the implementation
- [ ] If violated, note what needs fixing

If no compliance checklist exists in WM (e.g., task skipped WF_ARCH_REVIEW): use the generic checks in 2a only.

## Compliance Verification

If WM contains a Compliance Checklist (from WF_ARCH_REVIEW):
- Verify each checklist item against the implementation
- Reference DOM_* memories for domain-specific validation rules
- Reference DEV_* memories for language-specific standards compliance

### 2c. Integration Completeness Check

For any new files or components created, verify they are wired in:

- [ ] New scripts/styles enqueued in the asset loader?
- [ ] New handlers/modules registered in the registration system?
- [ ] New templates/blocks discoverable by the template engine?
- [ ] New classes instantiated or autoloaded?
- [ ] New routes/endpoints registered with the framework?

Check FEATURE_[KEY] for the feature's specific integration points. Not all items apply to every project — use the ones relevant to your feature.

Integration completeness failures are silent — code works in isolation but is never loaded. This is the most common post-implementation defect.

## 3. Gherkin Spec Coverage Check

If the affected feature has existing Gherkin specs OR WM contains `gherkin_spec_update: true`:

### 3.0a. Check for Existing Specs

```
Glob(pattern="tests/specs/*[feature-key]*.feature")
mcp__plugin_swe_serena__list_memories(topic="spec")
```

### 3.0b. If Specs Exist — Verify Coverage

For each existing `.feature` file related to the affected feature:

1. **Read the spec** and extract all Given/When/Then/And steps
2. **Compare against changes made** — did this task add or modify behavior covered by the spec?
3. **Check for gaps:**
   - [ ] New behavior added that is NOT covered by existing spec scenarios → **spec update needed**
   - [ ] Existing spec scenarios that now behave differently due to changes → **spec update needed**
   - [ ] All changed behavior is covered by existing specs → **pass**

### 3.0c. If Spec Updates Needed

Invoke `/swe-gherkin-spec` to add new scenarios covering the new behavior, then invoke `/swe-gherkin-dev` to create matching tests.

**This is NOT optional when specs exist.** If a feature has Gherkin specs, every behavioral change must be reflected in both the specs and their tests.

### 3.0d. If No Specs Exist

Skip this section. Gherkin specs are enforced at WF_ARCH_REVIEW for new features. Existing features without specs are not retroactively required to add them (unless the user requests it).

---

## 4. Test Coverage Check

### 4a. Tests-as-Deliverable Verification

If the task deliverable IS tests (writing new tests, fixing tests, adding test coverage):

The tests themselves are not the verification. Verification means confirming the tests work correctly:

- [ ] Run the new/modified tests — they must execute without runtime errors
- [ ] Tests pass when they should pass (happy path assertions hold)
- [ ] Tests fail when they should fail (if feasible: temporarily break the feature under test and confirm the test catches it)
- [ ] No false positives (tests don't pass trivially or vacuously)

After confirming test behavior, skip to Section 5 (no browser verification needed for test-only deliverables).

---

### 4b. Standard Test Coverage (Non-Test Deliverables)

For multi-layer work or user-facing changes:

- [ ] Functional tests cover the feature?
- [ ] Visual regression tests if UI changed?
- [ ] Tests run and pass?

If automated tests exist, run them.

### 4c. Browser Verification Fallback (No Automated Tests)

If no automated tests exist for this feature, verify the work visually in the dev browser when a local environment is available.

#### Prerequisites

1. Check for local environment — look for local dev server URLs in FEATURE_[KEY], project config, or `.serena/` files. If no local environment is available, note it in WM and skip to Step 4.
2. Check for saved scenarios — call `mcp__browser-devtools__scenario-list()` first.

#### Verification Steps

| Step | Action |
|------|--------|
| 1 | Use scenarios first — if a saved scenario covers the flow you changed, run it with `scenario-run`. |
| 2 | Manual verification — if no scenario matches, navigate to the affected page(s), take an ARIA snapshot, and verify the changes are reflected in the UI. |
| 3 | Screenshot evidence — take a screenshot of the verified state for WM documentation. |
| 4 | Create scenario — if you performed manual steps useful for future verification, save them with `scenario-add`. |

See `REF_MCP_BROWSER_DEVTOOLS` for browser interaction rules and best practices.

If no local environment AND no automated tests: note in WM that verification was not possible and flag for user attention before proceeding.

## 5. Fix Violations

If any violations found, fix them before proceeding.

## 6. Update WM

Invoke `/swe-wm-update --from WF_VERIFY` — provides the complete checklist and template. The skill handles reading, validating, and writing WM comprehensively.

Also update if needed:

- **DOM_[X]:** If domain architecture changed
- **SYS_[X]:** If system components changed
- **INDEX_[X]:** If indexes need new entries

---

## Fixing Violations In Place

WF_VERIFY is edit-allowed. When verification finds a violation, **fix it in place** — do NOT bounce to WF_EXECUTE for a small correction. Make the edit, re-run the relevant check, and continue. The forced state bounce that previously made verify read-only is removed in v4.

Only leave WF_VERIFY when the fix is large enough to warrant re-planning (see below).

## Re-Scope Check Before Looping Back

If a fix exceeds the scope of a minor correction, re-classify rather than silently expanding:

- **Minor in-place fix** (≤5 files, existing functionality) → fix here in WF_VERIFY, no transition.
- **Fix grew large** (now >5 files, adds a module, or crosses 3+ layers) → route to **WF_CLASSIFY** so the Architecture Review Necessity Check (Step 3b) re-evaluates and sends it to WF_ARCH_REVIEW if warranted. Do NOT jump straight to a major rewrite from verify.
- A larger fix that is clearly still simple implementation work (not new design) may go to **WF_EXECUTE**.

## Routing

| Condition                               | Next Step                                    |
| --------------------------------------- | -------------------------------------------- |
| Minor violation — fixable in place (≤5 files, existing functionality) | Fix in WF_VERIFY (no transition) |
| Fix grew large (>5 files / new module / 3+ layers) — needs re-planning | `WF_CLASSIFY` (re-runs Step 3b) |
| Larger fix, still plain implementation (no new design) | `WF_EXECUTE`                      |
| Tests missing AND no browser verification possible   | `WF_EXECUTE`                      |
| Browser verification failed (visual defects found)   | Fix in WF_VERIFY, or `WF_EXECUTE` if larger |
| WM not updated                                       | Invoke `/swe-wm-update --from WF_VERIFY` |
| All clean, tests/browser verification pass, WM updated | `WF_DONE`                                  |

Update WM via `/swe-wm-update` before transitioning.
