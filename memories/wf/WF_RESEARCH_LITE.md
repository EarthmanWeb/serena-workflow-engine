# WF_RESEARCH_LITE - Minimal Research Path

Use only when user explicitly requests lite/quick research.

---

> **On step WF_RESEARCH_LITE**

## Purpose

Lightweight workflow for simple lookup/research tasks with minimal overhead.

## Qualifying Tasks

- "Find where X is"
- "Show me the code for Y"
- "What files contain Z"
- "How does X work" (exploration only)

## Execute (3 Steps)

### 1. Quick Context Check

Optional: check `list_memories()` for `DOM_*/REF_*` memories that may already answer the question before searching code.

```
# Only if feature location unknown:
mcp__plugin_swe_serena__read_memory("index/INDEX_FEATURES")  # Skip if you know the feature
```

### 2. Search & Find

Use targeted tools in this order:

1. `Glob` - Find files by pattern first
2. `get_symbols_overview` - Understand file structure
3. `find_symbol` - Get specific code (`include_body=true` only when needed)
4. `Grep` - Content search as fallback

Start narrow, expand only if needed. Use `head_limit` on searches. Zero context lines unless essential.

### 3. Report & Exit

- Provide findings directly
- No WM required for simple lookups

## Token Budget Target

**< 2,500 tokens total** for simple lookups

## Routing

| Condition              | Next Step      |
| ---------------------- | -------------- |
| Task expands scope     | `WF_CLASSIFY`  |
| Lookup complete        | Done           |

Update WM via /swe-wm-update before transitioning.
