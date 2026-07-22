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

## Browser Verification (MCP DevTools)

Use Browser DevTools MCP to verify in the live browser when the failure involves selectors, DOM elements, browser rendering, JavaScript errors, or browser-mediated processes. Do NOT rely solely on code analysis for these failure types — code analysis alone misses live-DOM state.

See `REF_MCP_BROWSER_DEVTOOLS` for full tool reference and scenarios-first rule.

### When to Use — Failure Type → Action

| Failure Type | Browser MCP Action |
|--------------|--------------------|
| Selector not found / stale selector | ARIA snapshot to discover actual element refs, roles, names |
| Element exists but interaction fails | AX tree snapshot with `checkOcclusion: true` to detect hidden/covered elements |
| JavaScript runtime error | `o11y_get-console-messages` to read browser console |
| AJAX/fetch failure | `o11y_get-http-requests` to inspect request/response |
| Page not rendering expected content | `a11y_take-aria-snapshot` for structure; screenshot only if visual |
| CSS/layout issue | `content_take-screenshot` after ARIA confirms structure |
| Form submission not working | ARIA snapshot → inspect form elements → check network requests |

### Browser-Aware TDD Cycle

When the bug is browser-related, augment the standard cycle:

1. RED — reproduce in browser via MCP:
   - Navigate to the problem page.
   - Take ARIA snapshot ALWAYS before screenshot.
   - Check console for errors.
   - Confirm the failure is visible in the live browser.
2. DEBUG — use MCP to identify root cause:
   - ARIA snapshot — expected elements present? Roles/names match selectors?
   - AX tree with `checkOcclusion` — element visible or hidden/covered?
   - Console messages — JS errors, warnings, failed assertions?
   - HTTP requests — API calls succeeding? Correct payloads?
   - Debug probes — set logpoints/tracepoints on suspected code paths.
3. GREEN — implement fix, verify in browser:
   - After code change, reload page and re-run ARIA snapshot.
   - Confirm the selector/element/behavior works in the live DOM.
   - Do NOT trust code analysis alone. Verify the fix renders correctly.
4. VERIFY — run automated tests AND browser check:
   - Run the test suite to confirm pass.
   - Also verify in browser — tests may mock what the browser does not.
5. REFACTOR — clean up only if needed.

### Scenarios-First Rule

Before using any `mcp__browser-devtools__*` tool directly:

1. Call `scenario-list()` first.
2. If a matching scenario exists, use `scenario-run()` instead.
3. Fall back to individual tools ONLY for one-off inspection.

### Key Browser MCP Tools for Debugging

- Page structure (ALWAYS first, NEVER screenshot): `mcp__browser-devtools__a11y_take-aria-snapshot({})`
- Layout/visibility: `mcp__browser-devtools__a11y_take-ax-tree-snapshot({ checkOcclusion: true })`
- Console errors: `mcp__browser-devtools__o11y_get-console-messages({})`
- Network failures: `mcp__browser-devtools__o11y_get-http-requests({ resourceType: "fetch" })`
- Non-blocking debug probes (no pause): `mcp__browser-devtools__debug_put-logpoint({ urlPattern: "app.js", lineNumber: 42, logExpression: "{ myVar }" })` then `mcp__browser-devtools__debug_get-probe-snapshots({})`
- Visual verification (LAST, only if needed): `mcp__browser-devtools__content_take-screenshot({ fullPage: true })`

### Selector Debugging Checklist

When a test fails because a selector does not match:

1. Do NOT guess. Take an ARIA snapshot of the live page.
2. Compare — match the snapshot's element refs/roles/names against the failing selector.
3. Check dynamic state — element may only exist after interaction (click, scroll, wait).
4. Check occlusion — `checkOcclusion: true` reveals if element is behind a modal/overlay.
5. Check timing — use `sync_wait-for-network-idle` before snapshotting if content loads async.

## RLVR Signal

- Type: `debug_iteration`. Impact: neutral.

## Routing

| Condition | Next State |
| --------- | ---------- |
| Bug fixed | `WF_EXECUTE` |
| Stuck/unclear | `WF_CLARIFY` |

Update WM via `/swe-wm-update` before transitioning.
