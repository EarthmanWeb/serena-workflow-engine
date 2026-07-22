---
name: WF_INIT — Session Initialization
description: Mandatory session entry point — spawned-agent bypass, init chain (WF_INIT → CLAUDE_OBLIGATIONS → WF_CLASSIFY), memory-discovery and symbol-extraction tooling.
metadata:
  type: workflow
---

# WF_INIT — Session Initialization

## Finding Memories

Consult memories before grepping the filesystem.

- `list_memories(topic="<prefix>")` — list a directory prefix (e.g. `ref`, `feature`). Prefix filter, NOT a keyword.
- `search_memories_by_name(query)` — find a memory by a keyword in its name (fuzzy fallback).
- `search_memories_by_front_matter(query)` — find a memory by what it is about (front-matter description/type).
- `read_memory(name)` — read a memory whose name you have.

Every `write_memory` MUST start with the standard front-matter block, then the body:

```
---
name: <short title>
description: <one sentence: what this memory is about>
metadata:
  type: <derived from directory prefix — ref→reference, feedback→feedback, feature→feature, dom→domain, project→project, …>
---
```

Run `/swe-memory-frontmatter` to audit/backfill front-matter across existing memories.

## Spawned-Agent Bypass

Check for spawned-agent status BEFORE initializing. You are a spawned agent when your initial prompt contains any of:

- `"You are a swarm agent"`
- `"BYPASS WF_INIT"`
- `"You are the [role] agent"`
- `"Do NOT follow CLAUDE.md workflow"`
- Agent role assignment from a coordinator (e.g. "You are r1", "You are agent-features")
- Explicit task-only instructions without a user conversation

If spawned agent:
- Skip this file, WF_CLASSIFY, and all workflow steps.
- Do NOT create a WM file. Do NOT read CLAUDE_OBLIGATIONS.
- Execute only the task in your initial prompt.
- Read Serena memories and use any tool immediately.

If NOT a spawned agent, continue below.

## Do Not Skip This Workflow

Every session runs the init chain — including meta-work, simple questions, continuing previous conversations, and any other interaction. Complexity, task TYPE, and speed are irrelevant.

These rationalizations are NEVER valid:

- "This is a simple task" — complexity is irrelevant. All tasks follow the workflow.
- "I already know what to do" — the workflow exists for consistency, not knowledge.
- "The user wants a quick answer" — speed does not override the init chain.
- "I can batch this with other calls" — do NOT combine workflow steps with task work.
- "CLAUDE_OBLIGATIONS doesn't apply here" — it always applies. Read it every time.
- "The hook didn't block me, so it's fine" — the hook allowlist (read_memory init-chain + ToolSearch) exists so WF_INIT can run, NOT so you can start task work before init completes. A misconfigured or disabled gate is not permission either.
- "This is an investigation / debugging / operational task, not code" — task TYPE is irrelevant. Inspecting a container, reading logs, running Bash, checking a database, and "just looking" are all task work. All task work waits for the init chain.

Any tool call that searches code, edits files, or does task work before the init chain completes is a violation. The hook cannot distinguish "reading for init" from "reading to skip init." You must.

## Mandatory Entry Point

The FIRST tool call of any session MUST be `mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_INIT")` — ALWAYS the fully-qualified name, NEVER bare `read_memory`.

- Serena MCP tools may be DEFERRED (schema not loaded). A bare call — or any call before its schema is fetched — fails with "No such tool available".
- Load the schema first: `ToolSearch("select:mcp__plugin_swe_serena__read_memory,mcp__plugin_swe_serena__list_memories")`, then read.
- If your first tool call is anything else (Bash, Read, Grep, Agent, another MCP tool), you have already violated this. Do NOT explain the skip — run the init chain.
- The PreToolUse gate is the backstop, but it can be misconfigured or absent in a given project; enforcement is YOUR obligation regardless of whether a hook stops you.

Init chain:

1. `mcp__plugin_swe_serena__read_memory("claude/CLAUDE_OBLIGATIONS")`
2. Proceed to WF_CLASSIFY (first post-init workflow state).

Do NOT respond to the user before completing the obligations read.

## Continuing a Previous Task

Complete the init chain (WF_INIT → CLAUDE_OBLIGATIONS → WF_CLASSIFY) first. Do NOT skip the init chain to reach WF_CONTINUE. When WF_CLASSIFY routes to WF_CONTINUE, re-research the knowledge base at that step:

1. `list_memories(topic="dom")` — load any DOM_* memories relevant to the task.
2. `list_memories(topic="ref")` — load any REF_* memories relevant to the task.
3. `list_memories(topic="dev")` — load any DEV_* memories relevant to the task.

## Symbol Extraction

Use Serena symbolic tools before reading full files:

- `get_symbols_overview` — understand file structure without reading it.
- `find_symbol` with `include_body=True` — read only the symbol you need.
- `find_referencing_symbols` — trace dependencies between symbols.
- `search_for_pattern` — targeted search when the symbol name is unknown.

### `depth` Levels

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

- When symbol extraction returns empty, fall back to `search_for_pattern` with regex.
- Read full files ONLY for config files, files with poor language server support, or when full file context is explicitly needed.

## Browser DevTools

- Call `scenario-list()` before any `mcp__browser-devtools__` tool.
- Use `scenario-run()` when a matching scenario exists.
- Fall back to individual tools ONLY for one-off inspection.

## Step Reporting

After reading any WF_* memory, output the step report line before any other output. For WF_INIT, include plugin version:

```
> **On step WF_INIT (v1.x.x)**
```

Proceed to WF_CLASSIFY.
