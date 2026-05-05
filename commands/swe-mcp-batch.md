# MCP Batch Recorder

Converts recent Browser DevTools MCP steps from the current conversation into a reusable scenario stored in `.browser-devtools-mcp/scenarios.json` and Serena memory.

## Arguments
- $ARGUMENTS: Name/description for the batch (e.g., "login to wp-admin", "navigate to CRM contacts")

## Instructions

### 1. Parse Arguments

Extract from `$ARGUMENTS`:
- **Batch name**: Derive an `MCP_{action}` name (e.g., `MCP_login`, `MCP_navigate_crm`)
- **Description**: One-line summary of what the batch does

### 2. Review Conversation Thread

Scan backwards through the current conversation for Browser DevTools MCP tool calls. Identify the sequence of steps that match what `$ARGUMENTS` describes:

- `navigation_go-to` calls — URLs navigated to
- `a11y_take-aria-snapshot` calls — ref discovery points
- `interaction_fill` calls — field values entered
- `interaction_click` calls — buttons/links clicked (note `waitForNavigation`)
- `interaction_select`, `interaction_hover` — other interactions
- `scenario-run` calls — prerequisite batches that were composed

For each interaction step, note:
- The **element name** from the ARIA snapshot (e.g., `"Username or Email Address"`, `"Log In"`)
- The **role** (button, textbox, link, etc.)
- The **value** used (for fill/select)
- Whether `waitForNavigation` was needed

### 3. Check for Existing Scenarios

```
mcp__browser-devtools__scenario-list()
```

If a scenario with this name already exists, ask the user whether to update or abort.

### 4. Build the Scenario Script

Convert the identified steps into an `execute` script using **dynamic ref discovery** (never hardcoded refs). Pattern:

```javascript
// Navigate
await callTool('navigation_go-to', { url: '...', includeSnapshot: true, snapshotOptions: { interactiveOnly: true } });

// Discover refs by name (from ARIA snapshot)
const snapshot = await callTool('a11y_take-aria-snapshot', { interactiveOnly: true }, true);
const refs = snapshot.refs || {};
let targetRef;
for (const [ref, info] of Object.entries(refs)) {
  if (info.name === 'Element Name From Thread') targetRef = ref;
}
if (!targetRef) throw new Error('Could not find element: Element Name From Thread');

// Interact (replay the steps from the thread)
await callTool('interaction_fill', { selector: targetRef, value: '...' });
await callTool('interaction_click', { selector: loginRef, waitForNavigation: true });

// Verify end state
const result = await callTool('a11y_take-aria-snapshot', { maxDepth: 1 }, true);
if (!result.output.includes('Expected Page Title')) {
  throw new Error('Batch failed. Expected: ... Got: ' + result.output.substring(0, 200));
}

return { status: 'success', page: 'Expected Page' };
```

If the thread showed a prerequisite batch (e.g., `MCP_login` was run first), compose it:

```javascript
await callTool('scenario-run', { name: 'MCP_login' });
// Then the steps from the thread...
```

### 5. Save the Scenario

```
mcp__browser-devtools__scenario-add({
  name: "MCP_{action}",
  description: "One-line description",
  script: "... the script from step 4 ...",
  scope: "project"
})
```

### 6. Test the Scenario

```
mcp__browser-devtools__scenario-run({ name: "MCP_{action}" })
```

Verify it completes successfully. If it fails, debug and fix the script.

### 7. Store in Serena Memory

```
mcp__plugin_swe_serena__write_memory({
  memory_name: "mcp/MCP_{action}",
  content: "... documentation following MCP_login pattern ..."
})
```

Include:
- Overview table (type, storage, invoke command, target URL, result)
- Numbered steps describing what the batch does
- Usage example (standalone + composed)
- Ref discovery strategy
- Prerequisites if any

### 8. Update MEMORY.md

Add entry under MCP Batch Scenarios section.

## Key Rules

- **Retroactive** — review conversation thread to extract steps already taken, do not re-execute them from scratch
- **NEVER hardcode element refs** (e1, e2) — discover by `name` property from ARIA snapshot
- **Use `MCP_` prefix** for all batch scenario names
- **Project scope** for all scenarios (not global)
- **Compose, don't duplicate** — if a batch needs login, call `MCP_login`, don't re-implement it
- **Verify end state** — every batch must confirm it landed where expected
- **Error with context** — throw errors that include what was found vs expected
