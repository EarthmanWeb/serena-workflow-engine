# WF_INIT — Session Initialization

---

## Spawned Agent Bypass

Check if you are a spawned agent before initializing. Your initial prompt contains any of:
- `"You are a swarm agent"`
- `"BYPASS WF_INIT"`
- `"You are the [role] agent"`
- `"Do NOT follow CLAUDE.md workflow"`
- Agent role assignment from a coordinator (e.g., "You are r1", "You are agent-features")
- Explicit task-only instructions without a user conversation

If spawned agent:
- Skip this file, WF_START, WF_CLASSIFY, and all workflow steps
- Do not create a WM file or read CLAUDE_OBLIGATIONS
- Execute only the task in your initial prompt
- You may read Serena memories and use any tool immediately

If not a spawned agent, continue below.

---

## Rules

- ALL tasks go through the workflow. No exceptions for "simple" tasks.
- Do not use allowed tools (Read, Grep, Glob, list_memories) for task work before init completes — they are infrastructure for init only.
- Follow each step sequentially. Do not batch workflow steps with implementation actions.

---

## Entry Point

1. Read obligations:
```
mcp__plugin_swe_serena__read_memory("claude/CLAUDE_OBLIGATIONS")
```

2. Read workflow start:
```
mcp__plugin_swe_serena__read_memory("wf/WF_START")
```

Then follow WF_START instructions completely.

---

## Continuing a Previous Task

**After completing the init chain** (WF_INIT → CLAUDE_OBLIGATIONS → WF_START), if WF_START routes to WF_CONTINUE, re-research the knowledge base at that step:

1. `list_memories(topic="dom")` — load any DOM_* memories relevant to the task
2. `list_memories(topic="ref")` — load any REF_* memories relevant to the task
3. `list_memories(topic="dev")` — load any DEV_* memories relevant to the task

Do NOT skip the init chain to get here. Complete WF_INIT → WF_START first, then WF_START will route to WF_CONTINUE where these steps run.

---

## Symbol Extraction

Use Serena symbolic tools before reading full files:

- `get_symbols_overview` — understand file structure without reading it
- `find_symbol` with `include_body=True` — read only the symbol you need
- `find_referencing_symbols` — trace dependencies between symbols
- `search_for_pattern` — targeted search when symbol name is unknown

### Multi-Level Extraction with `depth`

Both `get_symbols_overview` and `find_symbol` accept a `depth` parameter (default 0):

| depth | Returns |
|-------|---------|
| `0` | Top-level symbols only (classes, standalone functions, constants) |
| `1` | Top-level + immediate children (e.g. class methods, function-local variables) |
| `2+` | Deeper nesting levels |

### Language Server Coverage

| File Type | Symbol Quality | Notes |
|-----------|---------------|-------|
| **PHP** | Excellent | Functions, classes, variables, DOM elements in templates |
| **Python** | Excellent | Classes, functions, variables |
| **TypeScript/JavaScript** | Good | Named exports, classes, functions. jQuery wrappers may return empty |
| **Markdown** | Limited | Headings only (H2/H3 as symbols) |
| **SCSS/CSS** | Poor | Language server rarely exposes selectors or variables |
| **JSON/YAML/Config** | None | No symbolic structure — use `Read` or `search_for_pattern` |

When symbol extraction returns empty, fall back to `search_for_pattern` with regex. Only read full files for config files, files with poor language server support, or when full file context is explicitly needed.

---

## Browser DevTools

Before using any `mcp__browser-devtools__` tool, call `scenario-list()` first. Use `scenario-run()` if a matching scenario exists. Only fall back to individual tools for one-off inspection.

---

## Step Reporting

After reading any WF_* memory, output the step report line before any other output. For WF_INIT, include plugin version:

```
> **On step WF_INIT (v1.x.x)**
```

---

Proceed to WF_START.
