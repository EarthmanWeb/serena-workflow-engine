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

## Browser Verification (MCP DevTools)

When the failure involves **selectors, DOM elements, browser rendering, JavaScript errors, or browser-mediated processes**, use the Browser DevTools MCP to verify directly in the live browser instead of relying solely on code analysis.

See `REF_MCP_BROWSER_DEVTOOLS` for full tool reference and scenarios-first rule.

### When to Use Browser Verification

| Failure Type | Browser MCP Action |
|--------------|--------------------|
| Selector not found / stale selector | ARIA snapshot to discover actual element refs, roles, and names |
| Element exists but interaction fails | AX tree snapshot with `checkOcclusion: true` to detect hidden/covered elements |
| JavaScript runtime error | `o11y_get-console-messages` to read browser console |
| AJAX/fetch failure | `o11y_get-http-requests` to inspect request/response |
| Page not rendering expected content | `a11y_take-aria-snapshot` for structure, screenshot only if visual |
| CSS/layout issue | `content_take-screenshot` after ARIA confirms structure |
| Form submission not working | ARIA snapshot → inspect form elements → check network requests |

### Browser-Aware TDD Cycle

When the bug is browser-related, augment the standard TDD cycle:

```
1. RED: Reproduce in browser via MCP
   - Navigate to the problem page
   - Take ARIA snapshot (ALWAYS before screenshot)
   - Check console for errors
   - Confirm the failure is visible in the live browser

2. DEBUG: Use MCP to identify root cause
   - ARIA snapshot: Are expected elements present? Do roles/names match selectors?
   - AX tree with checkOcclusion: Is the element visible or hidden/covered?
   - Console messages: JS errors, warnings, failed assertions?
   - HTTP requests: Are API calls succeeding? Correct payloads?
   - Debug probes: Set logpoints/tracepoints on suspected code paths

3. GREEN: Implement fix, verify in browser
   - After code change, reload page and re-run ARIA snapshot
   - Confirm the selector/element/behavior now works in the live DOM
   - Don't trust code analysis alone — verify the fix renders correctly

4. VERIFY: Run automated tests AND browser check
   - Run the test suite to confirm pass
   - Also verify in browser that the fix holds (tests may mock what the browser doesn't)

5. REFACTOR: Clean up if needed
```

### Scenarios-First Rule

Before using any `mcp__browser-devtools__*` tool directly:

1. Call `scenario-list()` first
2. If a matching scenario exists, use `scenario-run()` instead
3. Only fall back to individual tools for one-off inspection

### Key Browser MCP Tools for Debugging

```
# Page structure (ALWAYS FIRST — not screenshot)
mcp__browser-devtools__a11y_take-aria-snapshot({})

# Layout/visibility issues
mcp__browser-devtools__a11y_take-ax-tree-snapshot({ checkOcclusion: true })

# Console errors
mcp__browser-devtools__o11y_get-console-messages({})

# Network failures
mcp__browser-devtools__o11y_get-http-requests({ resourceType: "fetch" })

# Non-blocking debug probes (no pause)
mcp__browser-devtools__debug_put-logpoint({ urlPattern: "app.js", lineNumber: 42, logExpression: "{ myVar }" })
mcp__browser-devtools__debug_get-probe-snapshots({})

# Visual verification (LAST — only if needed)
mcp__browser-devtools__content_take-screenshot({ fullPage: true })
```

### Selector Debugging Checklist

When a test fails because a selector doesn't match:

1. **Don't guess** — take an ARIA snapshot of the live page
2. **Compare** — match the snapshot's element refs/roles/names against the failing selector
3. **Check dynamic state** — element may only exist after interaction (click, scroll, wait)
4. **Check occlusion** — `checkOcclusion: true` reveals if element is behind a modal/overlay
5. **Check timing** — use `sync_wait-for-network-idle` before snapshotting if content loads async

## RLVR Signal

- **Type**: debug_iteration | **Impact**: neutral

## Routing

| Condition     | Next State   |
| ------------- | ------------ |
| Bug fixed     | `WF_EXECUTE` |
| Stuck/unclear | `WF_CLARIFY` |

Update WM via /swe-wm-update before transitioning.