---
name: WF_VERIFY Test Coverage Check
description: Test-deliverable vs standard test-coverage verification steps at WF_VERIFY, and the no-automated-tests fallback.
metadata:
  type: reference
obligations:
  - When the deliverable IS tests, run them and confirm they fail on a broken feature before trusting a pass — do not treat a trivial/vacuous pass as verification.
---

# WF_VERIFY — Test Coverage Check

## Tests-as-Deliverable Verification

When the task deliverable IS tests (writing new tests, fixing tests, adding coverage), the tests are not the verification — confirm the tests work correctly:

- Run the new/modified tests — they MUST execute without runtime errors.
- Tests pass when they should pass (happy-path assertions hold).
- Tests fail when they should fail (if feasible: temporarily break the feature under test and confirm the test catches it).
- No false positives (tests do not pass trivially or vacuously).

After confirming test behavior, skip to Memory & Doc-Claims Verification (`mem:wf/WF_VERIFY`). No browser verification for test-only deliverables.

## Standard Test Coverage (Non-Test Deliverables)

For multi-layer work or user-facing changes:

- Functional tests cover the feature?
- Visual regression tests if UI changed?
- Tests run and pass?

If automated tests exist, run them.

## No Automated Tests

If no automated tests exist for this feature, note in WM that automated verification was not possible and flag for user attention before proceeding.
