---
name: WF_VERIFY
description: Workflow state — verify work against obligations, architecture, specs, and tests; fix violations in place; route on completion.
metadata:
  type: workflow
---

# WF_VERIFY — Check Work

> **On step WF_VERIFY**

## 1. Re-read CLAUDE_OBLIGATIONS

Read `claude/CLAUDE_OBLIGATIONS` via `mcp__plugin_swe_serena__read_memory`.

Check for violations:

- Used inappropriate type assertions (e.g. `as any`)?
- Created files without permission?
- Guessed paths without Serena?

## 2. Architecture & Compliance Check

Read via `mcp__plugin_swe_serena__read_memory`:

- `arch/ARCH_INDEX`
- `feature/FEATURE_DEV_STANDARDS`

### 2a. Generic Layer Verification

- Components follow documented layer patterns?
- Functions follow coding standards?
- Data flow follows architecture documentation?

### 2b. Compliance Checklist Verification

Read `## Compliance Checklist` from WM (written at WF_ARCH_REVIEW Step 2c).

Per checklist item:

- Verify it was satisfied in the implementation.
- If violated, note what needs fixing.

If no compliance checklist exists in WM (task skipped WF_ARCH_REVIEW): use 2a generic checks only.

Compliance verification when WM contains a Compliance Checklist:

- Verify each checklist item against the implementation.
- Reference `DOM_*` memories for domain-specific validation rules.
- Reference `DEV_*` memories for language-specific standards compliance.

### 2c. Integration Completeness Check

For any new file or component created, verify it is wired in:

- New scripts/styles enqueued in the asset loader?
- New handlers/modules registered in the registration system?
- New templates/blocks discoverable by the template engine?
- New classes instantiated or autoloaded?
- New routes/endpoints registered with the framework?

Check `FEATURE_[KEY]` for the feature's specific integration points. Apply only items relevant to the feature.

Integration completeness failures are silent — code works in isolation but is never loaded. This is the most common post-implementation defect; do NOT skip this check.

## 3. Gherkin Spec Coverage Check

Run when the affected feature has existing Gherkin specs OR WM contains `gherkin_spec_update: true`.

### 3.0a. Check for Existing Specs

- `Glob(pattern="tests/specs/*[feature-key]*.feature")`
- `mcp__plugin_swe_serena__list_memories(topic="spec")`

### 3.0b. If Specs Exist — Verify Coverage

For each existing `.feature` file related to the affected feature:

1. Read the spec; extract all Given/When/Then/And steps.
2. Compare against changes made — did this task add or modify behavior covered by the spec?
3. Check for gaps:
   - New behavior added NOT covered by existing spec scenarios → spec update needed.
   - Existing spec scenarios that now behave differently due to changes → spec update needed.
   - All changed behavior covered by existing specs → pass.

### 3.0c. If Spec Updates Needed

Invoke `/swe-gherkin-spec` to add scenarios covering the new behavior, then `/swe-gherkin-dev` to create matching tests.

This is NOT optional when specs exist. When a feature has Gherkin specs, every behavioral change MUST be reflected in both the specs and their tests.

### 3.0d. If No Specs Exist

Skip this section. Gherkin specs are enforced at WF_ARCH_REVIEW for new features. Do NOT retroactively require specs on existing features without specs unless the user requests it.

## 4. Test Coverage Check

### 4a. Tests-as-Deliverable Verification

When the task deliverable IS tests (writing new tests, fixing tests, adding coverage), the tests are not the verification — confirm the tests work correctly:

- Run the new/modified tests — they MUST execute without runtime errors.
- Tests pass when they should pass (happy-path assertions hold).
- Tests fail when they should fail (if feasible: temporarily break the feature under test and confirm the test catches it).
- No false positives (tests do not pass trivially or vacuously).

After confirming test behavior, skip to Section 5. No browser verification for test-only deliverables.

### 4b. Standard Test Coverage (Non-Test Deliverables)

For multi-layer work or user-facing changes:

- Functional tests cover the feature?
- Visual regression tests if UI changed?
- Tests run and pass?

If automated tests exist, run them.

### 4c. Browser Verification Fallback (No Automated Tests)

If no automated tests exist for this feature, verify visually in the dev browser when a local environment is available.

Prerequisites:

1. Check for local environment — look for local dev server URLs in `FEATURE_[KEY]`, project config, or `.serena/` files. If none available, note it in WM and skip to Step 4.
2. Check for saved scenarios — call `mcp__browser-devtools__scenario-list()` first.

Verification steps:

| Step | Action |
|------|--------|
| 1 | Use scenarios first — if a saved scenario covers the changed flow, run it with `scenario-run`. |
| 2 | Manual verification — if no scenario matches, navigate to the affected page(s), take an ARIA snapshot, verify changes are reflected in the UI. |
| 3 | Screenshot evidence — take a screenshot of the verified state for WM documentation. |
| 4 | Create scenario — if manual steps are useful for future verification, save them with `scenario-add`. |

See `REF_MCP_BROWSER_DEVTOOLS` for browser interaction rules.

If no local environment AND no automated tests: note in WM that verification was not possible and flag for user attention before proceeding.

## 5. Fix Violations

Fix all found violations before proceeding.

## 6. Update WM

Invoke `/swe-wm-update --from WF_VERIFY` — provides the complete checklist and template; handles reading, validating, and writing WM.

Also update if needed:

- **DOM_[X]:** domain architecture changed.
- **SYS_[X]:** system components changed.
- **INDEX_[X]:** indexes need new entries.

## Fixing Violations In Place

WF_VERIFY is edit-allowed. When verification finds a violation, fix it in place. Do NOT bounce to WF_EXECUTE for a small correction — make the edit, re-run the relevant check, continue.

Leave WF_VERIFY only when the fix is large enough to warrant re-planning (see Re-Scope Check).

## Re-Scope Check Before Looping Back

When a fix exceeds the scope of a minor correction, re-classify rather than silently expand:

- **Minor in-place fix** (≤5 files, existing functionality) → fix here in WF_VERIFY, no transition.
- **Fix grew large** (>5 files, adds a module, or crosses 3+ layers) → route to `WF_CLASSIFY` so the Architecture Review Necessity Check (Step 3b) re-evaluates and sends to WF_ARCH_REVIEW if warranted. Do NOT jump straight to a major rewrite from verify.
- Larger fix that is clearly still simple implementation work (not new design) → `WF_EXECUTE`.

## Routing

| Condition | Next Step |
| --------- | --------- |
| Minor violation — fixable in place (≤5 files, existing functionality) | Fix in WF_VERIFY (no transition) |
| Fix grew large (>5 files / new module / 3+ layers) — needs re-planning | `WF_CLASSIFY` (re-runs Step 3b) |
| Larger fix, still plain implementation (no new design) | `WF_EXECUTE` |
| Tests missing AND no browser verification possible | `WF_EXECUTE` |
| Browser verification failed (visual defects found) | Fix in WF_VERIFY, or `WF_EXECUTE` if larger |
| WM not updated | Invoke `/swe-wm-update --from WF_VERIFY` |
| All clean, tests/browser verification pass, WM updated | `WF_DONE` |

Update WM via `/swe-wm-update` before transitioning.
