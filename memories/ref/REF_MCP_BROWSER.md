# REF_MCP_BROWSER - Browser DevTools MCP Reference

Browser DevTools MCP (`browser-devtools-mcp`) provides programmatic browser control for debugging, testing, and exploration.

**MCP server name:** `browser-devtools` (registered in `.mcp.json`)
**Tool namespace:** `mcp__browser-devtools__*`
**Scenario storage:** `.browser-devtools-mcp/scenarios.json`

---

## Available Batch Scenarios

| Scenario | Invoke | Description |
|----------|--------|-------------|
| `MCP_login` | `scenario-run(name: "MCP_login")` | Login to WP admin as claude_admin |

Each scenario is documented in Serena memory as `mcp/MCP_{name}`.

### Creating New Batches

Use the `/swe-mcp-batch` skill to interactively record new multi-step browser interactions:

```
/swe-mcp-batch navigate to CRM contacts page
```

The skill will:
1. Walk through the steps interactively in the browser
2. Discover element refs dynamically via ARIA snapshots (never hardcoded)
3. Build a composable scenario script
4. Save to `.browser-devtools-mcp/scenarios.json` via `scenario-add`
5. Document in Serena memory as `mcp/MCP_{action}`

### Using Batches

```javascript
// Standalone tool call:
mcp__browser-devtools__scenario-run({ name: "MCP_login" })

// Inside an execute batch (composing scenarios):
await callTool('scenario-run', { name: 'MCP_login' });
// ... then continue with additional steps
```

### Listing Available Batches

```
mcp__browser-devtools__scenario-list()
```

---

## When to Use Browser MCP

### Use For:

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

**Default: Code analysis first. Browser MCP only if runtime verification needed.**

---

## Core Tool Patterns

### Navigation

```
mcp__browser-devtools__navigation_go-to({ url: "http://pleasurehuntfestival.local/..." })
```

### Page Inspection (ALWAYS snapshot first, NOT screenshot)

```
mcp__browser-devtools__a11y_take-aria-snapshot({ interactiveOnly: true })
mcp__browser-devtools__a11y_take-ax-tree-snapshot()  // for layout/bounding boxes
mcp__browser-devtools__content_take-screenshot()     // only for visual verification
```

### Element Interaction (use refs from ARIA snapshot)

```
mcp__browser-devtools__interaction_click({ selector: "e1" })
mcp__browser-devtools__interaction_fill({ selector: "e2", value: "text" })
mcp__browser-devtools__interaction_hover({ selector: "e3" })
mcp__browser-devtools__interaction_select({ selector: "e4", value: "option" })
```

### Batch Execution (major token saver)

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

### Observability

```
mcp__browser-devtools__o11y_get-console-messages({ type: "error" })
mcp__browser-devtools__o11y_get-http-requests({ resourceType: "fetch" })
mcp__browser-devtools__o11y_get-web-vitals()
```

### Scenarios (reusable batches)

```
mcp__browser-devtools__scenario-run({ name: "MCP_login" })
mcp__browser-devtools__scenario-list()
mcp__browser-devtools__scenario-add({ name: "MCP_x", description: "...", script: "..." })
```

---

## Key Rules

- **ARIA snapshot first** — always `a11y_take-aria-snapshot` before interacting, never guess selectors from screenshots
- **Refs are ephemeral** — `e1`, `e2` change between snapshots; never hardcode in scenarios (discover by `name` property)
- **Use `execute` for multi-step** — batches multiple calls into one, saves ~78% tokens vs individual calls
- **`waitForNavigation: true`** on clicks that navigate — ensures page loads before next action
- **Scenarios compose** — `callTool('scenario-run', { name: 'MCP_login' })` inside an execute block

---

## Context Cost

| Action | Cost | Use When |
|--------|------|----------|
| ARIA snapshot | ~500 tokens | Page structure discovery |
| click/fill/hover | ~20 tokens | Known element interaction |
| execute batch | ~100 tokens | Multi-step flows (huge savings) |
| screenshot | ~100 tokens | Visual verification only |
| console messages | ~50 tokens | Error investigation |

---

## Key Debugging Workflow

1. **Navigate** to problem page
2. **Get ARIA snapshot** — returns element refs
3. **Check console** for errors
4. **Inspect network** for failed requests
5. **Take screenshot** only for visual verification
