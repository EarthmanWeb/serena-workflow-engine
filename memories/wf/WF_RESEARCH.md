# WF_RESEARCH - Research Only

> **On step WF_RESEARCH**

---

## Verify Before Assert

Research findings ARE factual claims. Any statement about backend or environment state (DB contents, existing environments, container state, remote data) must be preceded by a verification call (`wp_cli`, `terminus`, `docker`, logs) in the same turn. If you cannot verify, label the finding "unverified" — never present plausible inference as fact.

---

## For Questions/Exploration Without Code Changes

### Step 1: Check Knowledge Base First

Before exploring code, check if existing memories answer the question:

```
list_memories(topic="dom")       # Domain behavior docs
list_memories(topic="ref")       # Reference patterns
list_memories(topic="feature")   # Feature configs
```

Read any memories relevant to the research question. These may contain file paths, architecture notes, and behavioral patterns that shortcut code exploration.

### Step 2: Explore with Serena Tools

If memories do not fully answer the question, use Serena tools to explore:

- `mcp__plugin_swe_serena__find_symbol`
- `mcp__plugin_swe_serena__get_symbols_overview`
- `mcp__plugin_swe_serena__search_for_pattern`

### Step 3: Report Findings

Provide findings directly to the user.

## Rules

- No code changes in this path
- No file creation
- Information gathering only

## Routing

| Condition                            | Next Step     |
| ------------------------------------ | ------------- |
| Research complete, user wants changes | `WF_CLASSIFY` |
| Research complete, no changes needed  | `WF_DONE`     |

If the user wants to proceed with implementation based on research findings, route to `WF_CLASSIFY` to classify the task and load feature context.

Update WM via /swe-wm-update before transitioning.
