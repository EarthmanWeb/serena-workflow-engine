---
name: REF_MCP_BROWSER_DEVTOOLS
description: Browser DevTools MCP — tool reference, scenario automation, session isolation for parallel agents, debugging workflows
type: reference
---

# REF_MCP_BROWSER_DEVTOOLS - Browser DevTools MCP Reference

Browser DevTools MCP (`@ironbee-ai/devtools`) provides Playwright-powered browser
control for debugging, testing, and exploration.

**MCP server name:** `browser-devtools` (registered in `.mcp.json`)
**Tool namespace:** `mcp__browser-devtools__*`
**Scenario storage:** `.ironbee-devtools/scenarios.json`

---

## Scenarios-First Rule

**Before using ANY `mcp__browser-devtools__` tool (navigation, interaction,
screenshot, etc.), you MUST first call:**

```
mcp__browser-devtools__scenario-list()
```

**Check if a saved scenario already handles what you need** (login, navigation,
common flows). If a matching scenario exists, use
`mcp__browser-devtools__scenario-run({ name: "..." })` instead of individual
tool calls.

**Individual browser tool calls (click, fill, navigate) are fragile and can crash
the browser.** Scenarios batch steps into a single resilient call with error
handling, sleeps, and recovery logic built in.

**Rules:**

- NEVER call `navigation_go-to`, `interaction_click`, `interaction_fill`, or
  other browser tools directly without first checking `scenario-list`
- ALWAYS prefer `scenario-run` over manual step-by-step browser interaction
- If no scenario exists for your flow, create one with `scenario-add` for reuse
- Only fall back to individual tools for one-off inspection (e.g. a single
  `a11y_take-aria-snapshot` after a scenario completes)

---

## When to Use

### Use Browser DevTools MCP For:

- 500/API errors requiring runtime inspection
- Visual/CSS issues requiring rendered output
- JavaScript debugging in browser
- Console/network inspection
- Manual testing and exploration
- Screenshots for documentation

### When NOT to Use:

- Syntax errors — read error message, find file:line
- Logic bugs with clear stack trace — read function, trace data flow
- Build errors — check build output

**Default: Code analysis first. MCP only if runtime verification needed.**

---

## Authentication & Login Scenarios

**STOP — before navigating to ANY authenticated page, check for a login
scenario:**

```
mcp__browser-devtools__scenario-list()
```

If a login scenario exists, run it. If none exists:

1. **Check project auth documentation first.** Look for:
   - `DOM_*` or `REF_*` memories describing authentication flows
   - Project README or CLAUDE.md for login instructions
   - `.env` or config files for dev credentials / test accounts
2. **Create a login scenario** using `scenario-add` after performing the login
   manually once. This ensures all future sessions (including parallel agents)
   reuse the same auth flow.
3. **Never hardcode credentials in tool calls.** Put them in the scenario script
   where they can be maintained in one place.

### Session Isolation for Parallel Agents

When multiple agents need authenticated access simultaneously, uncoordinated
logins can invalidate each other's sessions (each login creates a new server-side
session, expiring the previous one).

**Solution — storageState pattern:**

1. **First agent** runs a login scenario. After successful login, the scenario
   saves browser state (cookies + localStorage) via `storageState()` to an auth
   cache file (e.g. `.ironbee-devtools/.auth/{siteKey}.json`).
2. **Subsequent agents** run the same login scenario. The scenario detects saved
   state, restores cookies via `page.context().addCookies()`, verifies the
   session is still valid, and returns early — no new login needed.
3. **Freshness check:** Saved state should expire after a configurable period
   (e.g. 1 hour). Expired state triggers a fresh login.
4. **Fallback:** If filesystem caching is unavailable, in-memory
   `globalThis.__mcpAuth[siteKey]` cache works within the same MCP server
   process.

**Rules for parallel agents:**

- ALWAYS use login scenarios — never manually navigate to login pages
- NEVER login as the same user in parallel without session reuse
- One login, many consumers — first agent creates session, others reuse it
- Auth cache files (`.ironbee-devtools/.auth/`) should be gitignored

### Login Scenario Template

When creating a new login scenario for a project, follow this pattern:

```javascript
// Template: adapt URLs, selectors, and credentials to your project
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

**Adapt this template to your project's auth flow.** Check project-specific
`DOM_*`, `REF_*`, or `SYS_*` memories for the correct URLs, selectors, and
test credentials.

---

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

---

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

**Selectors:** Use refs from ARIA snapshot (`e1`, `@e1`, `ref=e1`) or
Playwright expressions (`getByRole('button', { name: 'Login' })`,
`getByLabel('Email')`).

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
mcp__browser-devtools__scenario-run({ name: "..." })
mcp__browser-devtools__scenario-add({ name: "...", description: "...", script: "..." })
```

---

## Key Rules

1. **ARIA snapshot first** — always `a11y_take-aria-snapshot` before interacting.
   Never guess selectors from screenshots.
2. **Refs are ephemeral** — `e1`, `e2` change between snapshots. Never hardcode
   refs in scenarios; discover elements by `name`, `role`, or `label` properties.
3. **Use `execute` for multi-step** — batches multiple calls into one, saves ~78%
   tokens vs individual calls.
4. **`waitForNavigation: true`** on clicks that navigate — ensures page loads
   before next action.
5. **Scenarios compose** — `callTool('scenario-run', { name: '...' })` inside an
   execute block chains reusable flows.
6. **Scenarios-first** — always check `scenario-list` before manual browser
   interaction.

---

## Efficient Workflows

### Navigate + Verify

```
navigation_go-to → sync_wait-for-network-idle → a11y_take-aria-snapshot
```

### Interact with discovered elements

```
a11y_take-aria-snapshot → interaction_click { selector: ref } → sync_wait-for-network-idle
```

### Debug network/console issues

```
o11y_get-console-messages
o11y_get-http-requests { resourceType: "fetch" }
```

---

## Key Debugging Workflow

1. **Navigate to problem page**
   ```
   navigation_go-to({ url: "https://..." })
   ```

2. **Get ARIA snapshot** (ALWAYS FIRST — not screenshot)
   ```
   a11y_take-aria-snapshot({})
   ```

3. **Check console for errors**
   ```
   o11y_get-console-messages({})
   ```

4. **Inspect network requests**
   ```
   o11y_get-http-requests({ resourceType: "fetch" })
   ```

5. **Take screenshot** (only if visual verification needed)
   ```
   content_take-screenshot({ fullPage: true })
   ```

---

## Selector Priority

1. **ARIA snapshot refs** (`e1`, `e2`) — primary method
2. **Playwright expressions** (`getByRole(...)`, `getByLabel(...)`) — semantic
3. **CSS selectors** (`#id`, `.class`) — last resort

**NEVER guess selectors from screenshots.** Always take a snapshot first.

---

## Creating New Scenarios

After performing browser steps manually in a conversation:

1. **Extract the navigation, interaction, and verification steps**
2. **Build a scenario script** with dynamic ref discovery (never hardcoded refs)
3. **Save** via `scenario-add({ name: "MCP_action_name", description: "...", script: "..." })`
4. **Test** via `scenario-run({ name: "MCP_action_name" })`
5. **Document** in a project memory if the scenario is complex

### Naming Convention

- Login scenarios: `login_{app_or_site}`
- Navigation flows: `navigate_{destination}`
- Form fills: `fill_{form_name}`
- Test flows: `test_{feature}`

---

## Browser DevTools vs Automated Tests

| Scenario | Use |
|----------|-----|
| Interactive debugging | Browser DevTools MCP |
| Console/network inspection | Browser DevTools MCP |
| Manual exploration | Browser DevTools MCP |
| Automated test suite | Project test framework (Playwright, Cypress, etc.) |
| CI/CD testing | Automated test framework |
