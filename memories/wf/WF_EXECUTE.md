---
name: WF_EXECUTE
description: Workflow state — do the work. Tool routing, feature/WM verification, layered implementation, Serena edit-tool signatures, parallel execution, next-step routing.
metadata:
  type: workflow
---

# WF_EXECUTE — Do The Work

> **On step WF_EXECUTE**

## Tool Routing & Verify-Before-Assert

- Use the sanctioned MCP tool first when one covers the operation: `wp_cli` for WordPress/DB, `swe-wm` for Working Memory, Serena memory tools for `.serena` memories.
- NEVER hand-roll a Bash equivalent: no `docker exec ... wp`, no raw `mysql`, no `Write` into memory dirs. Known workaround patterns are hard-denied by the Bash policy gate.
- If the sanctioned tool errors, FIX its configuration (e.g. re-run `/swe-wp-cli-setup`). A broken sanctioned path is a blocker to repair, NEVER a license to work around it.
- Precede any factual claim about backend/environment state (DB contents, existing environments, container state, remote data) with a verification call (`wp_cli`, `terminus`, `docker`, `sps_log`/QM) in the SAME turn.
- If you cannot verify, label the statement "unverified" or ask. NEVER assert unverified state as fact.

## Feature Memory Verification

Check WM for `Feature Key(s)`. For each key, verify `FEATURE_[KEY]` is read.

| Condition                   | Action                    |
| --------------------------- | ------------------------- |
| All feature memories loaded | Continue below            |
| Feature memories not loaded | Read them now (below)     |
| WM has no Feature Key(s)    | Go to `WF_CLASSIFY`       |

```
mcp__plugin_swe_serena__read_memory("index/INDEX_FEATURES")
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY1]")
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY2]")
```

Proceed only after all feature memories are loaded.

## WM Check

- Verify WM exists and reflects the current task before starting work.
- If WM is stale or missing, invoke `/swe-wm-update --from WF_EXECUTE`.
- Update WM (via the skill): before starting significant work; after completing each subtask; when task state changes; before transitioning to another WF_* step.

## Before Starting Work

If multi-layer (touches >1 architectural layer), read `arch/ARCH_INDEX`.

For each layer, load context:

```
mcp__plugin_swe_serena__read_memory("sys/SYS_[SYSTEM]")               # System docs
mcp__plugin_swe_serena__read_memory("ref/REF_[PATTERN]")              # Coding patterns
mcp__plugin_swe_serena__read_memory("dom/DOM_[DOMAIN]")              # Domain behavior
mcp__plugin_swe_serena__read_memory("feature/FEATURE_DEV_STANDARDS")  # Dev standards index
```

Load language-specific `DEV_*` for affected languages:

```
mcp__plugin_swe_serena__read_memory("dev/DEV_PHP")           # If touching PHP
mcp__plugin_swe_serena__read_memory("dev/DEV_JAVASCRIPT")    # If touching JS
```

Do NOT write code until relevant memories are loaded.

## Multi-Layer Implementation

1. Read architecture docs (`ARCH_INDEX`, `SYS_*`, `DOM_*`).
2. Understand data flow from `ARCH_INDEX`.
3. Implement each layer following patterns from `SYS_*` and `REF_*`.
4. Read `REF_TESTING`, implement tests, run and verify.

## Single-Layer Implementation

Use Serena tools directly:

1. `mcp__plugin_swe_serena__find_symbol` — locate code.
2. `mcp__plugin_swe_serena__get_symbols_overview` — file structure.
3. `Edit` / `mcp__plugin_swe_serena__replace_symbol_body` — make changes.

## Serena Edit Tool Signatures

> **⚠️ MANDATORY — fetch the live schema before your FIRST Serena write/edit call this session.**
> Applies to EVERY `mcp__plugin_swe_serena__*` tool that takes params: file edits (`replace_content`, `replace_symbol_body`, `insert_*`) AND memory tools (`edit_memory`, `write_memory`). They are deferred; schemas are NOT loaded until fetched. Guessing params (e.g. `pattern` instead of `needle`, or omitting `mode`) fails validation and wastes a turn.
>
> ```
> ToolSearch("select:mcp__plugin_swe_serena__replace_content")   # or edit_memory, write_memory, …
> ```
>
> - `edit_memory(memory_name, needle, repl, mode)` — same needle/repl/mode contract as `replace_content`, targets a memory by name.
> - `write_memory(memory_name, content)` — overwrites the WHOLE memory; no needle/repl/mode. Use when rewriting a memory wholesale.
>
> The reference below is a convenience cache; the fetched schema is the source of truth. On disagreement, trust the fetched schema and report the drift. (A post-failure hook auto-injects the correct signature for ANY Serena tool that fails a schema check — but fetch first so you do not waste the call.)

Do NOT guess parameter names. Correct signatures:

### `replace_content` — text/regex replacement (preferred for non-symbol edits: Markdown, config, prose)

| Param | Required | Notes |
| ----- | -------- | ----- |
| `relative_path` | ✅ | Path to the file |
| `needle` | ✅ | String OR regex to search for (NOT `pattern`) |
| `repl` | ✅ | Replacement string (regex backrefs: `$!1`, `$!2`, …) |
| `mode` | ✅ | `"literal"` or `"regex"` — REQUIRED, no default |
| `allow_multiple_occurrences` | ❌ | Default `false`; set `true` to replace every match |

```
mcp__plugin_swe_serena__replace_content(
    relative_path="memories/wf/WF_X.md",
    needle="old text or regex",
    repl="new text",
    mode="literal",          # or "regex"
)
```

> Error `2 validation errors … needle Field required … mode Field required` means you passed `pattern`/`repl` only. Re-call with `needle` + `repl` + `mode`. In `regex` mode, `needle` uses Python `re` syntax with DOTALL + MULTILINE; prefer `beginning.*?end` wildcards over quoting long spans.

### `replace_symbol_body` — replace a whole symbol body (functions, classes, methods)

| Param | Required | Notes |
| ----- | -------- | ----- |
| `name_path` | ✅ | Symbol path, e.g. `ClassName/method_name` |
| `relative_path` | ✅ | File containing the symbol |
| `body` | ✅ | New symbol body (verbatim, correctly indented) |

### `insert_before_symbol` / `insert_after_symbol`

| Param | Required | Notes |
| ----- | -------- | ----- |
| `name_path` | ✅ | Anchor symbol |
| `relative_path` | ✅ | File |
| `body` | ✅ | Content to insert |

**Tool choice:** code symbols → `replace_symbol_body` / `insert_*`; Markdown/config/prose or sub-symbol text → `replace_content` (or `Edit`). Fall back to `Edit`/`Read` ONLY when symbols cannot be resolved (per `CLAUDE_OBLIGATIONS`).

## Parallel Execution

For tasks with independent subtasks, use the Claude Code Agent tool:

```javascript
Agent({ description: "Task A", run_in_background: true, model: "sonnet",
  isolation: "worktree",
  prompt: "You are a subagent. BYPASS WF_INIT. [task]..." })
```

- Launch ALL agents in ONE message for parallel execution.
- Use `isolation: "worktree"` when agents edit overlapping files.
- Use `model: "haiku"` for read-only tasks, `"sonnet"` for implementation.
- Collect results from background task notifications, then synthesize.

## Rules

- Make ONLY approved changes.
- Do NOT expand scope without asking.
- Tests are required for functional code.
- Integration tests are required for components that interact with external systems.

### New File Creation

1. Check naming conventions from the relevant `DEV_*` memory.
2. Include required boilerplate from `DEV_*` (file headers, guards, defaults).
3. Register/wire the new file per `FEATURE_[KEY]` or `DOM_*` patterns.
4. Verify any compliance checklist items in WM.

Missing registration is the most common cause of "code is correct but doesn't work" failures.

## Next Step

| Condition                       | Read Next       |
| ------------------------------- | --------------- |
| Created/modified file           | `WF_CHECKPOINT` |
| Completed a phase               | `WF_CHECKPOINT` |
| All work done (including tests) | `WF_VERIFY`     |

1. Determine which condition applies.
2. Update WM with current progress.
3. Read that WF_* memory.
4. Report the new step to user.

Update WM via `/swe-wm-update` before transitioning.
