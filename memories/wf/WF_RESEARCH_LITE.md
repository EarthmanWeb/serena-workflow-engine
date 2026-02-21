# WF_RESEARCH_LITE - Minimal Research Path

---

## ⚠️ USER-REQUESTED MODE ONLY

**This workflow is ONLY available when the user explicitly requests it.**

Valid triggers:

- User says "/lite" or "use lite mode"
- User explicitly asks for "quick lookup" mode
- User specifically requests to skip WM

**NEVER auto-route to this workflow based on task classification.**
If no explicit user request → Use `WF_RESEARCH` instead.

---

> **🔎 On step WF_RESEARCH_LITE**

## Purpose

Lightweight workflow for simple lookup/research tasks when user explicitly requests minimal overhead.

## Qualifying Tasks

- "Find where X is"
- "Show me the code for Y"
- "What files contain Z"
- "How does X work" (exploration only)

## Disqualifying Conditions (Use Full Workflow Instead)

- Any code modification needed
- Multi-step implementation
- Cross-feature impact analysis
- Debugging/troubleshooting

## Execute (3 Steps Only)

### 1. Quick Context Check

```
# Only if feature location unknown:
mcp__plugin_swe_serena__read_memory("INDEX_FEATURES")  # Optional - skip if you know the feature
```

### 2. Search & Find

Use targeted tools in this order:

1. `Glob` - Find files by pattern first
2. `get_symbols_overview` - Understand file structure
3. `find_symbol` - Get specific code (with `include_body=true` only when needed)
4. `Grep` - Content search as fallback

**Search Strategy:**

- Start narrow, expand only if needed
- Use `head_limit` on searches
- Zero context lines unless essential

### 3. Report & Exit

- Provide findings directly
- No WM required for simple lookups
- If task expands scope → transition to `WF_CLASSIFY`

## Token Budget Target

**< 2,500 tokens total** for simple lookups

## Example Flow

```
User: "Find where event calendar is rendered"

1. Glob: **/*event*calendar*.php → files found
2. get_symbols_overview: main.php → methods listed  
3. find_symbol: get_event_calendar → body retrieved
4. Report: "Found at main.php:1060"

Total: ~2,000 tokens ✓
```

## NO Workflow Transitions Required

This is a terminal state for simple research. No further workflow transitions needed.
