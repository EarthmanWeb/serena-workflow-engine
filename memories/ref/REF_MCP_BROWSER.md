# REF_MCP_BROWSER - Browser MCP Reference

Browser MCP provides programmatic browser control for debugging, testing, and exploration.

---

## ⛔ STOP - READ CONFIG FIRST

**BEFORE ANY browser navigation to an authenticated page:**

```
mcp__serena__read_memory("SYS_MCP_BROWSER_CONFIG")
```

The config contains:

- Login URLs and credential locations
- Feature-to-login mappings
- Available MCP tool prefix (DevTools vs Playwright)

**DO NOT PROCEED without reading the config.**
**DO NOT improvise URLs or guess auth flows.**

---

## Available MCP Tools

Two browser MCP options may be available. Check SYS_MCP_BROWSER_CONFIG for which is configured:

| MCP             | Tool Prefix               | Best For                                      |
| --------------- | ------------------------- | --------------------------------------------- |
| Chrome DevTools | `mcp__chrome-devtools__*` | Runtime debugging, console/network inspection |
| Playwright      | `mcp__playwright__*`      | Automated testing, form filling, screenshots  |

**Use whichever is available.** Both provide similar core functionality.

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

- Syntax errors → read error message, find file:line
- Logic bugs with clear stack trace → read function, trace data flow
- Build errors → check build output

**Default: Code analysis first. Browser MCP only if runtime verification needed.**

---

## Context Strategy

| Action       | Context Cost | Use When                  |
| ------------ | ------------ | ------------------------- |
| `snapshot`   | ~500 tokens  | Page structure discovery  |
| `click`      | ~20 tokens   | Known element interaction |
| `fill`       | ~20 tokens   | Form input                |
| `evaluate`   | ~50 tokens   | Querying specific data    |
| `wait`       | ~10 tokens   | Confirming text/state     |
| `screenshot` | ~100 tokens  | Visual verification       |

---

## Common Tool Patterns

### Navigation

```
# Chrome DevTools
mcp__chrome-devtools__navigate_page({ "url": "https://..." })

# Playwright
mcp__playwright__browser_navigate({ "url": "https://..." })
```

### Page Inspection

```
# Chrome DevTools
mcp__chrome-devtools__take_snapshot()
mcp__chrome-devtools__take_screenshot({ "fullPage": true })

# Playwright
mcp__playwright__browser_snapshot()
mcp__playwright__browser_take_screenshot({ "fullPage": true })
```

### Element Interaction

```
# Chrome DevTools (uses UID from snapshot)
mcp__chrome-devtools__click({ "uid": "button-uid" })
mcp__chrome-devtools__fill({ "uid": "input-uid", "value": "text" })

# Playwright (uses ref from snapshot)
mcp__playwright__browser_click({ "element": "Submit button", "ref": "s1e5" })
mcp__playwright__browser_type({ "element": "Username field", "ref": "s1e3", "text": "admin" })
```

### Console/Network (DevTools only)

```
mcp__chrome-devtools__list_console_messages({ "types": ["error", "warn"] })
mcp__chrome-devtools__list_network_requests({ "resourceTypes": ["fetch", "xhr"] })
```

### JavaScript Evaluation

```
# Chrome DevTools
mcp__chrome-devtools__evaluate_script({ "function": "() => document.title" })

# Playwright
mcp__playwright__browser_evaluate({ "function": "() => document.title" })
```

---

## Key Debugging Workflow

1. **Read config** - `SYS_MCP_BROWSER_CONFIG`
2. **Navigate** to problem page
3. **Get snapshot** - Returns element refs/UIDs
4. **Check console** for errors (DevTools)
5. **Inspect network** for failed requests (DevTools)
6. **Take screenshot** for reference

---

## Selector Priority

1. **Snapshot ref/UID** - Primary method for element targeting
2. **evaluate with querySelector** - For complex queries

---

## Tips

- **Always get snapshot first** to discover element refs/UIDs
- **Use wait** after actions to confirm state changes
- **Check console errors** when page behavior is unexpected
- **Inspect network** for API failures or slow requests
- **Take screenshots** to document issues for later reference
