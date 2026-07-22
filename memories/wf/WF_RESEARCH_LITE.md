---
name: WF_RESEARCH_LITE
description: Minimal research path for simple lookup/exploration tasks; target < 2,500 tokens, no WM required.
metadata:
  type: workflow
---

# WF_RESEARCH_LITE — Minimal Research Path

> **On step WF_RESEARCH_LITE**

Enter ONLY when the user explicitly requests lite/quick research. Route anything larger to `WF_CLASSIFY`.

## Qualifying Tasks

- "Find where X is"
- "Show me the code for Y"
- "What files contain Z"
- "How does X work" (exploration only)

## Execute — 3 Steps

### 1. Quick Context Check

- Check `list_memories()` for `DOM_*`/`REF_*` memories that answer the question before searching code.
- Read `index/INDEX_FEATURES` ONLY when the feature location is unknown. Skip when you know the feature.

### 2. Search & Find

Use tools in this order; start narrow, expand ONLY if needed:

1. `Glob` — find files by pattern first
2. `get_symbols_overview` — understand file structure
3. `find_symbol` — get specific code; set `include_body=true` ONLY when needed
4. `Grep` — content search fallback

- Set `head_limit` on searches.
- Zero context lines unless essential.

### 3. Report & Exit

- Report findings directly.
- Do NOT create WM for simple lookups.

## Token Budget

- Target < 2,500 tokens total.

## Routing

| Condition          | Next Step     |
| ------------------ | ------------- |
| Task expands scope | `WF_CLASSIFY` |
| Lookup complete    | Done          |

Update WM via `/swe-wm-update` before transitioning.
