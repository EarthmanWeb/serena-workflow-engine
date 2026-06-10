# WF_DEBUG_TDD

> **On step WF_DEBUG_TDD**

---

## Purpose

Test-driven debugging workflow for failing tests or bugs.

## Entry

- **From**: WF_CLASSIFY
- **Triggers**: test_failure, bug_report, behavior_mismatch

## Step 0: Load Context

Before debugging, load relevant context:
- read_memory("feature/FEATURE_[KEY]") for the affected feature
- Check list_memories(topic="dom") for domain behavior docs — these describe expected behavior
- Check list_memories(topic="ref") for coding patterns in the affected area

## Required Actions

1. `reproduce_issue` - Confirm the failure/bug exists
2. `identify_root_cause` - Find the actual problem
3. `implement_fix` - Make minimal fix
4. `verify_fix` - Run tests to confirm fix works

## Permissions

- **Edit**: true | **Write**: true
- **Plan Mode**: never

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

## RLVR Signal

- **Type**: debug_iteration | **Impact**: neutral

## Routing

| Condition     | Next State   |
| ------------- | ------------ |
| Bug fixed     | `WF_EXECUTE` |
| Stuck/unclear | `WF_CLARIFY` |

Update WM via /swe-wm-update before transitioning.
