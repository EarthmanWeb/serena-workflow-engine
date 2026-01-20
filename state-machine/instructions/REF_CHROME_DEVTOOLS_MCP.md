# REF_CHROME_DEVTOOLS_MCP - Browser Debugging Reference

Chrome DevTools MCP provides browser control for debugging, testing, and exploration.

---

## ⛔ STOP - READ THIS FIRST

**This memory does NOT contain login URLs or credentials.**

**BEFORE ANY browser navigation to an authenticated page:**

```
mcp__serena__read_memory("SYS_[FEATURE]_LOGIN")
```

| Feature | Login Memory |
|---------|--------------|
| ICOLD | `SYS_ICOLD_LOGIN` |
| Builder | `SYS_BUILDER_LOGIN` |

**DO NOT PROCEED without reading the feature-specific login memory.**
**DO NOT improvise URLs or guess auth flows.**

---

## When to Use

### Use Chrome DevTools MCP For:
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

**Default: Code analysis first. MCP only if runtime verification needed.**

---

## Context Strategy

| Action | Context Cost | Use When |
|--------|--------------|----------|
| `take_snapshot` | ~500 tokens | Page structure discovery |
| `click` | ~20 tokens | Known element interaction |
| `fill` | ~20 tokens | Form input |
| `evaluate_script` | ~50 tokens | Querying specific data |
| `wait_for` | ~10 tokens | Confirming text/state |
| `take_screenshot` | ~100 tokens | Visual verification |

---

## Tool Reference

### Navigation

```json
mcp__chrome-devtools__navigate_page({ "url": "https://example.com" })
mcp__chrome-devtools__navigate_page({ "type": "back" })
mcp__chrome-devtools__navigate_page({ "type": "forward" })
mcp__chrome-devtools__navigate_page({ "type": "reload" })
```

### Page Inspection

```json
mcp__chrome-devtools__take_snapshot()  // Accessibility tree with UIDs
mcp__chrome-devtools__take_screenshot({ "fullPage": true })
mcp__chrome-devtools__take_screenshot({ "uid": "element-uid" })
```

### Element Interaction

```json
mcp__chrome-devtools__click({ "uid": "button-uid" })
mcp__chrome-devtools__click({ "uid": "link-uid", "dblClick": true })
mcp__chrome-devtools__fill({ "uid": "input-uid", "value": "text" })
mcp__chrome-devtools__hover({ "uid": "element-uid" })
```

### Form Operations

```json
mcp__chrome-devtools__fill_form({
  "elements": [
    { "uid": "username-input", "value": "admin" },
    { "uid": "password-input", "value": "secret" }
  ]
})
```

### Keyboard Input

```json
mcp__chrome-devtools__press_key({ "key": "Enter" })
mcp__chrome-devtools__press_key({ "key": "Control+A" })
mcp__chrome-devtools__press_key({ "key": "Escape" })
```

### Wait Operations

```json
mcp__chrome-devtools__wait_for({ "text": "Success", "timeout": 5000 })
```

### Console Inspection

```json
mcp__chrome-devtools__list_console_messages({ "types": ["error", "warn"] })
mcp__chrome-devtools__get_console_message({ "msgid": 1 })
```

### Network Inspection

```json
mcp__chrome-devtools__list_network_requests({ "resourceTypes": ["fetch", "xhr"] })
mcp__chrome-devtools__get_network_request({ "reqid": 1 })
```

### JavaScript Evaluation

```json
mcp__chrome-devtools__evaluate_script({
  "function": "() => document.title"
})
mcp__chrome-devtools__evaluate_script({
  "function": "() => document.querySelector('#result').textContent"
})
mcp__chrome-devtools__evaluate_script({
  "function": "(el) => el.innerText",
  "args": [{ "uid": "target-element" }]
})
```

### Tab Management

```json
mcp__chrome-devtools__list_pages()
mcp__chrome-devtools__select_page({ "pageIdx": 0 })
mcp__chrome-devtools__new_page({ "url": "https://example.com" })
mcp__chrome-devtools__close_page({ "pageIdx": 1 })
```

### Performance Tracing

```json
mcp__chrome-devtools__performance_start_trace({ "reload": true, "autoStop": true })
mcp__chrome-devtools__performance_stop_trace()
mcp__chrome-devtools__performance_analyze_insight({ "insightSetId": "...", "insightName": "LCPBreakdown" })
```

---

## Efficient Workflows

### Navigate + Verify (no snapshot needed)
```
navigate_page -> wait_for { text: "Page Title" }
```

### Interact with discovered elements
```
take_snapshot -> click { uid from snapshot } -> wait_for { text: "Done" }
```

### Query page data directly
```
evaluate_script { function: "() => document.title" }
```

### Debug network/console issues
```
list_console_messages { types: ["error"] }
list_network_requests { resourceTypes: ["fetch"] }
```

---

## Key Debugging Workflow

1. **Navigate to problem page**
   ```
   navigate_page({ url: "https://..." })
   ```

2. **Get page snapshot**
   ```
   take_snapshot()  // Returns accessibility tree with UIDs
   ```

3. **Check console for errors**
   ```
   list_console_messages({ types: ["error", "warn"] })
   ```

4. **Inspect network requests**
   ```
   list_network_requests({ resourceTypes: ["fetch", "xhr"] })
   ```

5. **Take screenshot for reference**
   ```
   take_screenshot({ fullPage: true })
   ```

---

## Selector Priority

1. **Snapshot UID** - Primary method for element targeting
2. **evaluate_script with querySelector** - For complex queries

---

## Chrome DevTools vs Automated Tests

| Scenario | Use |
|----------|-----|
| Interactive debugging | Chrome DevTools MCP |
| Console/network inspection | Chrome DevTools MCP |
| Manual exploration | Chrome DevTools MCP |
| Automated test suite | Playwright/Cypress tests |
| CI/CD testing | Automated test framework |
| Visual regression | Automated test framework |

---

## Tips

- **Always get snapshot first** to discover element UIDs
- **Use wait_for** after actions to confirm state changes
- **Check console errors** when page behavior is unexpected
- **Inspect network** for API failures or slow requests
- **Take screenshots** to document issues for later reference
