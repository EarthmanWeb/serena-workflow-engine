# WF_VERIFY

> **✔️ On step WF_VERIFY**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Verify implementation against requirements.

## Entry

- **From**: WF_EXECUTE, WF_CHECKPOINT
- **Triggers**: implementation_complete

## Required Actions

1. `run_tests` - Execute test suite
2. `verify_requirements` - Check all requirements met
3. `check_standards` - Confirm REF_DEV_STANDARDS compliance

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: never

## Verification Checklist

- [ ] All tests pass
- [ ] Requirements from WORKING_MEMORY satisfied
- [ ] No regressions introduced
- [ ] Code follows standards
- [ ] No security vulnerabilities

## Transitions

| Condition | Next State |
|-----------|------------|
| passed | WF_DONE |
| failed | WF_EXECUTE |

## RLVR Signal

- **Type**: verify_check | **Impact**: bonus_if_first_try (+0.1)

First-time verification pass indicates good planning and execution.

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Verification passed | `WF_DONE` |
| Verification failed | `WF_EXECUTE` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
