---
name: WF_DEBUG_TDD
description: Test-driven debugging workflow state for failing tests, bugs, and behavior mismatches.
metadata:
  type: workflow
---

# WF_DEBUG_TDD

> **On step WF_DEBUG_TDD**

## Entry

- From: `WF_CLASSIFY`.
- Triggers: `test_failure`, `bug_report`, `behavior_mismatch`.

## Permissions

- Edit: true. Write: true. Plan Mode: never.

## Step 0: Load Context

Before debugging, load:

- `read_memory("feature/FEATURE_[KEY]")` for the affected feature.
- `list_memories(topic="dom")` — domain behavior docs describing expected behavior.
- `list_memories(topic="ref")` — coding patterns for the affected area.

## Required Actions

1. `reproduce_issue` — confirm the failure/bug exists.
2. `identify_root_cause` — find the actual problem.
3. `implement_fix` — make the minimal fix.
4. `verify_fix` — run tests to confirm the fix works.

## TDD Cycle

1. RED — confirm test fails / bug reproduces.
2. DEBUG — identify root cause.
3. GREEN — implement minimal fix.
4. VERIFY — confirm test passes / bug fixed.
5. REFACTOR — clean up only if needed.

## Debugging Rules

- Start with reproduction.
- Use logging/tracing sparingly.
- Fix the root cause, NEVER symptoms.
- Do NOT add defensive code. Fail fast.

## RLVR Signal

- Type: `debug_iteration`. Impact: neutral.

## Routing

| Condition | Next State |
| --------- | ---------- |
| Bug fixed | `WF_EXECUTE` |
| Stuck/unclear | `WF_CLARIFY` |

Update WM via `/swe-wm-update` before transitioning.
