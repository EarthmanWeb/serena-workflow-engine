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

Read via `mcp__plugin_swe_serena__read_memory`: `arch/ARCH_SWE`, `feature/FEATURE_DEV_STANDARDS`.

### 2a. Generic Layer Verification

- Components follow documented layer patterns?
- Functions follow coding standards?
- Data flow follows architecture documentation?

### 2b. Compliance Checklist Verification

Read `## Compliance Checklist` from WM (written at WF_ARCH_REVIEW Step 2c).

- Verify each checklist item against the implementation; if violated, note what needs fixing.
- If no compliance checklist exists in WM (task skipped WF_ARCH_REVIEW): use 2a generic checks only.
- Every item MUST be either checked done or explicitly waived with a reason. An UNCHECKED item with no waiver is a BLOCKER — resolve before `WF_DONE`.
- A `(mem:<name>)`-cited planned-rule item verifies against the memory's BODY, never the digest alone — read the body now if WF_EXECUTE never did (on-miss), then check the implementation against it. Marking a planned item done from the front-matter digest without a body read is a violation; fix by reading the body and re-verifying.
- Reference `DOM_*` memories for domain-specific validation rules, `DEV_*` for language-specific standards compliance.

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

Run when the affected feature has existing Gherkin specs OR WM contains `gherkin_spec_update: true`. Full procedure: `mem:ref/REF_WF_VERIFY_GHERKIN_COVERAGE`.

## 4. Test Coverage Check

Run the applicable test-verification steps (tests-as-deliverable, standard coverage, no-automated-tests fallback): `mem:ref/REF_WF_VERIFY_TEST_COVERAGE`.

## 5. Memory & Doc-Claims Verification

- List memories consulted this task. For each, state: confirmed against code / corrected / not exercised.
- Verify ZERO `pending` rows remain in WM `## Doc Claims Used` (parser: `hooks/swe_hooks/core/doc_claims.py`). A row showing a discovered true value with NO memory correction this session is a BLOCKER.
- Flush the WM doc-drift list: correct EACH drifted memory before `WF_DONE`.

## 6. Fix Violations

Fix all found violations before proceeding.

- Verification follow-ups that need a user choice go into WM `## Open Decisions`; unchecked entries block completion at the stop gate.

## 7. Update WM

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

| Condition                                                              | Next Step                                                                            |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Minor violation — fixable in place (≤5 files, existing functionality)  | Fix in WF_VERIFY (no transition)                                                     |
| Fix grew large (>5 files / new module / 3+ layers) — needs re-planning | `WF_CLASSIFY` (re-runs Step 3b)                                                      |
| Larger fix, still plain implementation (no new design)                 | `WF_EXECUTE`                                                                         |
| Tests missing AND no automated verification possible                   | `WF_EXECUTE`                                                                         |
| `pending` rows in `## Doc Claims Used`, or doc-drift list unflushed    | Resolve here — confirm/correct each claim, fix each drifted memory. BLOCKS `WF_DONE` |
| WM not updated                                                         | Invoke `/swe-wm-update --from WF_VERIFY`                                             |
| All clean, tests pass, zero pending doc claims, WM updated             | `WF_DONE`                                                                            |

Update WM via `/swe-wm-update` before transitioning.

Backward routes (`→ WF_EXECUTE`, `→ WF_CLASSIFY`) advance via the read itself — both are declared `readBackward` entries for `WF_VERIFY`. If the hook reports "inspecting — no transition" (loop guard), call `mcp__plugin_swe_swe-wm__swe_wm_transition(session_id="<id>", target_state="<STATE>", reason="<why>")` as the explicit fallback.
