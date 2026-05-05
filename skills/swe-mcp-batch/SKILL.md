# MCP Batch Recorder

Record a multi-step browser interaction into a reusable MCP scenario, stored in both the Browser DevTools MCP scenario system (`.browser-devtools-mcp/scenarios.json`) and Serena memory.

## Arguments
- $ARGUMENTS: Description of the batch to create (e.g., "login to wp-admin", "navigate to CRM contacts page")

## Instructions

Creating a new MCP batch scenario. Follow these steps exactly:

### 1. Parse the Request

Extract from `$ARGUMENTS`:
- **Batch name**: Derive an `MCP_{action}` name (e.g., `MCP_login`, `MCP_navigate_crm`)
- **Steps**: What browser actions are needed (navigate, fill, click, wait, verify)
- **Starting state**: Does this batch depend on another batch? (e.g., needs login first)

### 2. Check for Existing Scenarios

```
mcp__browser-devtools__scenario-list()
```

- If the requested batch already exists, inform the user and ask if they want to update it
- If the batch depends on login, note that `MCP_login` can be composed via `callTool('scenario-run', { name: 'MCP_login' })`

### 3. Interactive Discovery

Execute the steps interactively using individual MCP tool calls to discover the correct selectors:

1. **Navigate** to the target page using `navigation_go-to`
2. **Snapshot** using `a11y_take-aria-snapshot` with `interactiveOnly: true` to get refs
3. **Record ref mappings** — note which `name` property maps to each form field/button (do NOT hardcode ref IDs like `e1`, `e2` — they are ephemeral)
4. **Interact** — fill fields, click buttons using the discovered refs
5. **Verify** — take a final snapshot to confirm the expected end state

### 4. Build the Scenario Script

Write the scenario using dynamic ref discovery (NOT hardcoded refs). Pattern:

```javascript
// Navigate
await callTool('navigation_go-to', { url: '...', includeSnapshot: true, snapshotOptions: { interactiveOnly: true } });

// Discover refs by name
const snapshot = await callTool('a11y_take-aria-snapshot', { interactiveOnly: true }, true);
const refs = snapshot.refs || {};
let targetRef;
for (const [ref, info] of Object.entries(refs)) {
  if (info.name === 'Expected Name') targetRef = ref;
}
if (!targetRef) throw new Error('Could not find target element');

// Interact
await callTool('interaction_fill', { selector: targetRef, value: '...' });
await callTool('interaction_click', { selector: targetRef, waitForNavigation: true });

// Verify
const result = await callTool('a11y_take-aria-snapshot', { maxDepth: 1 }, true);
if (!result.output.includes('Expected Page')) throw new Error('Verification failed');

return { status: 'success', page: 'Expected Page' };
```

### 5. Composing Batches

If the batch requires a prior batch (like login), compose them:

```javascript
// Run prerequisite batch
await callTool('scenario-run', { name: 'MCP_login' });
// Then continue with this batch's steps...
```

### 6. Save the Scenario

```
mcp__browser-devtools__scenario-add({
  name: "MCP_{action}",
  description: "Clear one-line description",
  script: "... the script from step 4 ...",
  scope: "project"
})
```

### 7. Test the Scenario

```
mcp__browser-devtools__scenario-run({ name: "MCP_{action}" })
```

Verify it completes successfully.

### 8. Store in Serena Memory

```
mcp__plugin_swe_serena__write_memory({
  memory_name: "mcp/MCP_{action}",
  content: "... documentation following MCP_login pattern ..."
})
```

Include in the memory:
- Overview table (type, storage, invoke command, target URL)
- How it works (numbered steps)
- Usage example
- Ref discovery strategy
- Any prerequisites (e.g., "Requires MCP_login first")

### 9. Update MEMORY.md

Add entry under MCP Batch Scenarios section.

## Key Rules

- **NEVER hardcode element refs** (e1, e2) — always discover by `name` property from ARIA snapshot
- **Use `MCP_` prefix** for all batch scenario names
- **Project scope** for all scenarios (not global)
- **Compose, don't duplicate** — if a batch needs login, call `MCP_login`, don't re-implement it
- **Verify end state** — every batch must confirm it landed where expected
- **Error with context** — throw errors that include what was found vs expected
