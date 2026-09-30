---
name: WF_EXECUTE Serena Edit Tool Signatures
description: Param cheat-sheet for Serena edit/memory MCP tools (replace_content, replace_symbol_body, insert_before/after_symbol) — open when making a Serena write/edit call during WF_EXECUTE.
obligations:
  - Fetch the live schema via ToolSearch before the FIRST Serena write/edit call each session — this cheat-sheet is a convenience cache, not the source of truth.
metadata:
  type: reference
---

# Serena Edit Tool Signatures

Do NOT guess parameter names.

### `replace_content` — text/regex replacement (Markdown, config, prose)

| Param                        | Required | Notes                                                |
| ---------------------------- | -------- | ---------------------------------------------------- |
| `relative_path`              | ✅       | Path to the file                                     |
| `needle`                     | ✅       | String OR regex to search for (NOT `pattern`)        |
| `repl`                       | ✅       | Replacement string (regex backrefs: `$!1`, `$!2`, …) |
| `mode`                       | ✅       | `"literal"` or `"regex"` — REQUIRED, no default      |
| `allow_multiple_occurrences` | ❌       | Default `false`; set `true` to replace every match   |

```
mcp__plugin_swe_serena__replace_content(
    relative_path="memories/wf/WF_X.md",
    needle="old text or regex",
    repl="new text",
    mode="literal",          # or "regex"
)
```

Error `2 validation errors … needle Field required … mode Field required` means `pattern`/`repl` only were passed. Re-call with `needle` + `repl` + `mode`. In `regex` mode, `needle` uses Python `re` syntax with DOTALL + MULTILINE; prefer `beginning.*?end` wildcards over quoting long spans.

### `replace_symbol_body` — replace a whole symbol body (functions, classes, methods)

| Param           | Required | Notes                                          |
| --------------- | -------- | ---------------------------------------------- |
| `name_path`     | ✅       | Symbol path, e.g. `ClassName/method_name`      |
| `relative_path` | ✅       | File containing the symbol                     |
| `body`          | ✅       | New symbol body (verbatim, correctly indented) |

### `insert_before_symbol` / `insert_after_symbol`

| Param           | Required | Notes             |
| --------------- | -------- | ----------------- |
| `name_path`     | ✅       | Anchor symbol     |
| `relative_path` | ✅       | File              |
| `body`          | ✅       | Content to insert |

### Memory tools

- `edit_memory(memory_name, needle, repl, mode)` — same needle/repl/mode contract as `replace_content`, targets a memory by name.
- `write_memory(memory_name, content)` — overwrites the WHOLE memory; no needle/repl/mode. Use when rewriting a memory wholesale.

**Tool choice:** code symbols → `replace_symbol_body` / `insert_*`; Markdown/config/prose or sub-symbol text → `replace_content` (or `Edit`). Fall back to `Edit`/`Read` ONLY when symbols cannot be resolved (per `CLAUDE_OBLIGATIONS`).

A post-failure hook auto-injects the correct signature for ANY Serena tool that fails a schema check — fetch first so the call is not wasted.
