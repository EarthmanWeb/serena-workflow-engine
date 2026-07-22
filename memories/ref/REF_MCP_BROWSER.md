---
name: REF_MCP_BROWSER
description: Browser DevTools MCP — tool reference, scenario automation, session isolation for parallel agents, debugging workflows
metadata:
  type: reference
---

# REF_MCP_BROWSER — Browser DevTools MCP Reference

- Server: `browser-devtools` (`@ironbee-ai/devtools`), registered in `.mcp.json`.
- Tool namespace: `mcp__browser-devtools__*`.
- Scenario storage: `.ironbee-devtools/scenarios.json`.

## Scenarios-First Rule

- Before ANY `mcp__browser-devtools__*` tool (navigation, interaction, screenshot), MUST first call `mcp__browser-devtools__scenario-list()`.
- If a saved scenario matches the need (login, navigation, common flow), run `mcp__browser-devtools__scenario-run({ name: "..." })` instead of individual tool calls.
- NEVER call `navigation_go-to`, `interaction_click`, `interaction_fill`, or other browser tools directly without first calling `scenario-list`.
- ALWAYS prefer `scenario-run` over manual step-by-step interaction. Individual browser tool calls are fragile and can crash the browser; scenarios batch steps into one resilient call with error handling, sleeps, and recovery.
- When no scenario exists for the flow, create one with `scenario-add` for reuse.
- Fall back to individual tools ONLY for one-off inspection (e.g. a single `a11y_take-aria-snapshot` after a scenario completes).

## When to Use

| Condition | Action |
|-----------|--------|
| 500/API error needing runtime inspection | Use Browser DevTools MCP |
| Visual/CSS issue needing rendered output | Use Browser DevTools MCP |
| JavaScript debugging in browser | Use Browser DevTools MCP |
| Console/network inspection | Use Browser DevTools MCP |
| Manual testing / exploration | Use Browser DevTools MCP |
| Screenshots for documentation | Use Browser DevTools MCP |
| Syntax error | Read error message, find file:line — do NOT use MCP |
| Logic bug with clear stack trace | Read function, trace data flow — do NOT use MCP |
| Build error | Check build output — do NOT use MCP |

- Default: code analysis first. Use MCP ONLY when runtime verification is needed.

## Authentication & Login Scenarios

- STOP before navigating to ANY authenticated page. First call `mcp__browser-devtools__scenario-list()`.
- If a login scenario exists, run it. If none exists:
  1. Check project auth documentation first: `DOM_*`/`REF_*` memories describing auth flows, project README/CLAUDE.md login instructions, `.env`/config files for dev credentials or test accounts.
  2. Create a login scenario with `scenario-add` after performing login manually once, so all future sessions (including parallel agents) reuse the same auth flow.
  3. NEVER hardcode credentials in tool calls. Put them in the scenario script, maintained in one place.

### Session Isolation for Parallel Agents

- Uncoordinated logins invalidate each other's sessions: each login creates a new server-side session, expiring the previous one.
- storageState pattern:
  1. First agent runs a login scenario; on success the scenario saves cookies + localStorage via `storageState()` to an auth cache file (e.g. `.ironbee-devtools/.auth/{siteKey}.json`).
  2. Subsequent agents run the same login scenario; it detects saved state, restores cookies via `page.context().addCookies()`, verifies the session is still valid, and returns early — no new login.
  3. Freshness check: saved state expires after a configurable period (e.g. 1 hour). Expired state triggers a fresh login.
  4. Fallback: if filesystem caching is unavailable, use in-memory `globalThis.__mcpAuth[siteKey]` within the same MCP server process.
- ALWAYS use login scenarios. NEVER manually navigate to login pages.
- NEVER login as the same user in parallel without session reuse.
- One login, many consumers: first agent creates the session, others reuse it.
- Gitignore auth cache files (`.ironbee-devtools/.auth/`).

### Login Scenario Template

Adapt URLs, selectors, credentials to the project. Check project `DOM_*`/`REF_*`/`SYS_*` memories for correct URLs, selectors, and test credentials.

```javascript
const siteKey = 'my-app-local';
const authDir = '.ironbee-devtools/.auth';
const authFile = `${authDir}/${siteKey}.json`;
const loginUrl = 'https://your-app.local/login';
const dashboardIndicator = 'Dashboard'; // text visible after successful login

// 1. Check for cached session
const fs = require('fs');
if (fs.existsSync(authFile)) {
  const saved = JSON.parse(fs.readFileSync(authFile, 'utf8'));
  const age = Date.now() - (saved.timestamp || 0);
  if (age < 3600000) { // 1 hour
    await page.context().addCookies(saved.cookies);
    await page.goto(loginUrl.replace('/login', '/dashboard'));
    const text = await page.textContent('body');
    if (text.includes(dashboardIndicator)) {
      return { status: 'reused', siteKey };
    }
  }
}

// 2. Fresh login
await page.goto(loginUrl);
await page.fill('[name="username"]', 'your-test-user');
await page.fill('[name="password"]', 'your-test-password');
await page.click('button[type="submit"]');
await page.waitForLoadState('networkidle');

// 3. Save session for reuse
const cookies = await page.context().cookies();
const storage = await page.evaluate(() => JSON.stringify(localStorage));
if (!fs.existsSync(authDir)) fs.mkdirSync(authDir, { recursive: true });
fs.writeFileSync(authFile, JSON.stringify({
  cookies, storage, timestamp: Date.now()
}));

return { status: 'logged_in', siteKey };
```

## Context Strategy

| Action | Token Cost | Use When |
|--------|-----------|----------|
| `a11y_take-aria-snapshot` | ~500 | Page structure discovery (USE FIRST) |
| `interaction_click` | ~20 | Known element interaction |
| `interaction_fill` | ~20 | Form input |
| `execute` | ~100 | Batching multiple steps (saves ~78% vs individual calls) |
| `sync_wait-for-network-idle` | ~10 | Confirming page load |
| `content_take-screenshot` | ~100 | Visual verification (USE LAST) |
| `o11y_get-console-messages` | ~50 | Error investigation |

## Tool Reference

### Navigation

```
mcp__browser-devtools__navigation_go-to({ url: "https://..." })
mcp__browser-devtools__navigation_go-back-or-forward({ direction: "back" })
mcp__browser-devtools__navigation_reload({})
```

### Page Inspection

```
mcp__browser-devtools__a11y_take-aria-snapshot({})           // ARIA tree with refs (e1, e2, ...)
mcp__browser-devtools__a11y_take-ax-tree-snapshot({})        // Full AX tree with bounding boxes
mcp__browser-devtools__content_take-screenshot({ fullPage: true })
mcp__browser-devtools__content_get-as-html({ selector: "form" })
mcp__browser-devtools__content_get-as-text({})
```

### Element Interaction

```
mcp__browser-devtools__interaction_click({ selector: "e1" })      // ref from snapshot
mcp__browser-devtools__interaction_fill({ selector: "e2", value: "text" })
mcp__browser-devtools__interaction_hover({ selector: "e3" })
mcp__browser-devtools__interaction_select({ selector: "e4", values: ["option1"] })
mcp__browser-devtools__interaction_drag({ source: "e5", target: "e6" })
```

- Selectors: use refs from ARIA snapshot (`e1`, `@e1`, `ref=e1`) or Playwright expressions (`getByRole('button', { name: 'Login' })`, `getByLabel('Email')`).

### Keyboard Input

```
mcp__browser-devtools__interaction_press-key({ key: "Enter" })
mcp__browser-devtools__interaction_press-key({ key: "Control+A" })
```

### Synchronization

```
mcp__browser-devtools__sync_wait-for-network-idle({ timeoutMs: 15000 })
```

### Observability

```
mcp__browser-devtools__o11y_get-console-messages({})
mcp__browser-devtools__o11y_get-http-requests({ resourceType: "fetch" })
mcp__browser-devtools__o11y_get-web-vitals({})
```

### Batch Execution

```
mcp__browser-devtools__execute({
  code: `
    await callTool('navigation_go-to', { url: '...' });
    const snap = await callTool('a11y_take-aria-snapshot', { interactiveOnly: true }, true);
    await callTool('interaction_fill', { selector: 'e2', value: 'test' });
    await callTool('interaction_click', { selector: 'e6', waitForNavigation: true });
    return { status: 'done' };
  `
})
```

### Debug Probes

```
mcp__browser-devtools__debug_put-logpoint({ ... })
mcp__browser-devtools__debug_put-tracepoint({ ... })
mcp__browser-devtools__debug_get-probe-snapshots({})
```

### Scenarios

```
mcp__browser-devtools__scenario-list({})
mcp__browser-devtools__scenario-run({ name: "...", args: { key: "value" } })
mcp__browser-devtools__scenario-add({ name: "...", description: "...", script: "..." })
```

## Scenario Composition (Nested Recursion)

- Scenarios support nested `callTool('scenario-run', ...)` calls, max depth 5. Use existing scenarios as reusable macros.
- Check `scenario-list` first. When an existing scenario handles part of the flow (login, navigation, publish, dismiss modal), call it instead of inlining the logic.
- Compose, do NOT duplicate. A new scenario needing admin access calls `wp-admin-navigate` (which itself calls `wp-login-local` if needed) — do NOT copy-paste login + navigation code.
- Extract shared patterns. When 2+ scenarios share the same block (publish flow, modal dismiss), extract it into a standalone scenario and have both call it.
- Pass args through. Nested scenarios receive `args` from the parent call:
  ```javascript
  await callTool('scenario-run', { name: 'wp-admin-navigate', args: { path: 'post-new.php?post_type=page', includeSnapshot: false } });
  ```
- Keep leaf scenarios focused: one thing well (login, dismiss modal, publish). Orchestration belongs in the caller.

Composition example (three levels of nesting, zero duplicated code):

```
wp-create-page (caller)
  → wp-admin-navigate (navigate + auto-login)
      → wp-login-local (auth + storageState reuse)
  → wp-dismiss-welcome (modal dismiss)
  → [fill page-specific fields]
  → wp-gutenberg-publish (2-click publish flow)
```

## Key Rules

- ARIA snapshot first: ALWAYS call `a11y_take-aria-snapshot` before interacting. NEVER guess selectors from screenshots.
- Refs are ephemeral: `e1`, `e2` change between snapshots. NEVER hardcode refs in scenarios; discover elements by `name`, `role`, or `label`.
- Use `execute` for multi-step: batches calls into one, saves ~78% tokens vs individual calls.
- Set `waitForNavigation: true` on clicks that navigate, so the page loads before the next action.
- Scenarios compose: use `callTool('scenario-run', { name: '...' })` to chain reusable flows. ALWAYS prefer an existing scenario over inlining duplicate logic.
- Scenarios-first: ALWAYS check `scenario-list` before manual browser interaction.

## Efficient Workflows

- Navigate + verify: `navigation_go-to` → `sync_wait-for-network-idle` → `a11y_take-aria-snapshot`.
- Interact with discovered elements: `a11y_take-aria-snapshot` → `interaction_click { selector: ref }` → `sync_wait-for-network-idle`.
- Debug network/console: `o11y_get-console-messages`; `o11y_get-http-requests { resourceType: "fetch" }`.

## Key Debugging Workflow

1. Navigate to problem page: `navigation_go-to({ url: "https://..." })`.
2. Get ARIA snapshot (ALWAYS FIRST, NOT screenshot): `a11y_take-aria-snapshot({})`.
3. Check console for errors: `o11y_get-console-messages({})`.
4. Inspect network requests: `o11y_get-http-requests({ resourceType: "fetch" })`.
5. Take screenshot ONLY if visual verification needed: `content_take-screenshot({ fullPage: true })`.

## Selector Priority

1. ARIA snapshot refs (`e1`, `e2`) — primary.
2. Playwright expressions (`getByRole(...)`, `getByLabel(...)`) — semantic.
3. CSS selectors (`#id`, `.class`) — last resort.

- NEVER guess selectors from screenshots. ALWAYS take a snapshot first.

## Creating New Scenarios

After performing browser steps manually:

1. Extract the navigation, interaction, and verification steps.
2. Build a scenario script with dynamic ref discovery. NEVER hardcode refs.
3. Save via `scenario-add({ name: "MCP_action_name", description: "...", script: "..." })`.
4. Test via `scenario-run({ name: "MCP_action_name" })`.
5. Document in a project memory when the scenario is complex.

### Naming Convention

- Login scenarios: `login_{app_or_site}`.
- Navigation flows: `navigate_{destination}`.
- Form fills: `fill_{form_name}`.
- Test flows: `test_{feature}`.

## Browser DevTools vs Automated Tests

| Scenario | Use |
|----------|-----|
| Interactive debugging | Browser DevTools MCP |
| Console/network inspection | Browser DevTools MCP |
| Manual exploration | Browser DevTools MCP |
| Automated test suite | Project test framework (Playwright, Cypress, etc.) |
| CI/CD testing | Automated test framework |
