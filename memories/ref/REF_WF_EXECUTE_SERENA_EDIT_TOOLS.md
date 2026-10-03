---
name: WF_EXECUTE Serena Memory Tool Signatures
description: Param cheat-sheet for Serena memory MCP edit tools (edit_memory, write_memory) — open when making a Serena memory write/edit call during WF_EXECUTE.
obligations:
  - Fetch the live schema via ToolSearch before the FIRST Serena memory write/edit call each session — this cheat-sheet is a convenience cache, not the source of truth.
metadata:
  type: reference
---

# Serena Memory Tool Signatures

Serena = memory ops ONLY. Code edits use native `Edit`/`Write` — see `mem:claude/CLAUDE_OBLIGATIONS`. Do NOT guess parameter names below.

### `edit_memory` — patch a memory by name

| Param                        | Required | Notes                                                |
| ---------------------------- | -------- | ---------------------------------------------------- |
| `memory_name`                | ✅       | Memory to edit                                       |
| `needle`                     | ✅       | String OR regex to search for (NOT `pattern`)        |
| `repl`                       | ✅       | Replacement string (regex backrefs: `$!1`, `$!2`, …) |
| `mode`                       | ✅       | `"literal"` or `"regex"` — REQUIRED, no default      |
| `allow_multiple_occurrences` | ❌       | Default `false`; set `true` to replace every match   |

```
mcp__plugin_swe_serena__edit_memory(
    memory_name="wf/WF_X",
    needle="old text or regex",
    repl="new text",
    mode="literal",          # or "regex"
)
```

Error `2 validation errors … needle Field required … mode Field required` means `pattern`/`repl` only were passed. Re-call with `needle` + `repl` + `mode`. In `regex` mode, `needle` uses Python `re` syntax with DOTALL + MULTILINE; prefer `beginning.*?end` wildcards over quoting long spans.

### `write_memory` — overwrite a memory wholesale

`write_memory(memory_name, content)` — no needle/repl/mode. Use when rewriting a memory in full.

A post-failure hook auto-injects the correct signature for any Serena memory tool that fails a schema check — fetch first so the call is not wasted.
