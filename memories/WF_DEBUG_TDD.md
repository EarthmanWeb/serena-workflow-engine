# WF_DEBUG_TDD

> **🐛 On step WF_DEBUG_TDD**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Test-driven debugging workflow for failing tests or bugs.

## Entry

- **From**: WF_CLASSIFY
- **Triggers**: test_failure, bug_report, behavior_mismatch

## Required Actions

1. `reproduce_issue` - Confirm the failure/bug exists
2. `identify_root_cause` - Find the actual problem
3. `implement_fix` - Make minimal fix
4. `verify_fix` - Run tests to confirm fix works

## Permissions

- **Edit**: true | **Write**: true
- **Plan Mode**: never
  - Reason: Debugging requires rapid iteration, not upfront planning

## TDD Cycle

```
1. RED: Confirm test fails / bug reproduces
2. DEBUG: Identify root cause
3. GREEN: Implement minimal fix
4. VERIFY: Confirm test passes / bug fixed
5. REFACTOR: Clean up if needed
```

## Debugging Guidelines

- Start with reproduction
- Use logging/tracing sparingly
- Fix root cause, not symptoms
- Don't add defensive code (fail fast)

## Transitions

| Condition | Next State |
|-----------|------------|
| fixed | WF_EXECUTE |
| needs_help | WF_CLARIFY |

## RLVR Signal

- **Type**: debug_iteration | **Impact**: neutral

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Bug fixed | `WF_EXECUTE` |
| Stuck/unclear | `WF_CLARIFY` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
