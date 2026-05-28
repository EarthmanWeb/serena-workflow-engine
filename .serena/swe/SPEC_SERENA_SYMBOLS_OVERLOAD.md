# SPEC_SERENA_SYMBOLS_OVERLOAD — get_symbols_overview Intermittent Overload

**Status:** INVESTIGATION COMPLETE
**Created:** 2026-05-27
**Component:** Serena SWE Plugin (MCP) — `get_symbols_overview` tool
**Symptom:** Intermittent stop hook trigger / overload in VSCode Claude Code chat

---

## Problem

`get_symbols_overview` intermittently causes the VSCode Claude Code chat to either:
- Trigger a stop hook (forced continuation loop)
- Appear to overload / freeze the session

## Source Code Locations

| File | Purpose |
|------|---------|
| `serena/tools/symbol_tools.py` (L48-118) | `GetSymbolsOverviewTool.apply()` implementation |
| `serena/tools/tools_base.py` (L237-322) | `Tool.apply_ex()` — central execution with timeout |
| `serena/task_executor.py` (L74-85) | `TaskExecutor` — queue + timeout enforcement |
| `serena/config/serena_config.py` | Default config values |
| `serena/mcp.py` (L176-247) | MCP server tool wrapper |
| `hooks/stop/swe_stop_continue_working.py` | Stop hook that blocks premature stops |

Base path: `~/.cache/uv/archive-v0/TX4kFk_ZXFuWK_Xrm1gAA/lib/python3.11/site-packages/serena/`

## Root Cause Analysis

### Cause 1: Response Size → max_tokens → Stop Hook Loop (PRIMARY)

**Probability: HIGH**

`get_symbols_overview` returns up to **150,000 characters** of JSON (`default_max_tool_answer_chars`). When called on a large file (especially PHP/TypeScript at `depth >= 1`), the response floods the context window. If Claude then hits `max_tokens` in its reply, the stop hook (`swe_stop_continue_working.py`) detects `max_tokens` and **blocks the stop** — forcing Claude to continue in a degraded state with a bloated context.

**Chain:** Large file → huge JSON → context fills → `max_tokens` → stop hook blocks → forced continuation loop

**Evidence:**
- Stop hook unconditionally blocks on `max_tokens` hit (treats it as incomplete work)
- No distinction between "tool output overflow" vs "genuinely incomplete work"
- 150K char default is excessive for context-limited chat sessions

### Cause 2: Language Server Timeout (240s)

**Probability: MEDIUM**

Default `tool_timeout` is 240 seconds. If the language server is slow (indexing, restarting, or processing a large file), the MCP call blocks for up to 4 minutes. VSCode Claude Code chat appears frozen during this time.

**Config:** `SerenaConfig.tool_timeout = 240` (minimum: 10s)

### Cause 3: Language Server Crash → Restart → Retry

**Probability: MEDIUM**

If the language server terminates mid-operation, Serena catches `SolidLSPException`, restarts the server, and retries the full operation. This doubles wall-clock time and can cascade if the same file causes repeated crashes.

**Code path (tools_base.py):**
```python
except SolidLSPException as e:
    if e.is_language_server_terminated():
        self.agent.get_language_server_manager_or_raise().restart_language_server(affected_language)
        result = apply_fn(**kwargs)  # full retry
```

### Cause 4: Task Queue Serialization

**Probability: LOW-MEDIUM**

`TaskExecutor` runs tasks in a single-threaded queue. A slow `get_symbols_overview` blocks ALL subsequent Serena tool calls. When Claude issues parallel tool calls, they stack up behind the slow one.

### Cause 5: No Task Cancellation on Timeout

**Probability: LOW-MEDIUM**

From `task_executor.py:74-85`: when timeout fires, `TimeoutError` is raised to the caller but **the task itself continues running**. The language server keeps processing the stale request while new requests queue behind it, creating resource contention.

```python
def result(self, timeout: float | None = None) -> T:
    # If timeout is reached, TimeoutError is raised (but the task is not cancelled)
    return self.future.result(timeout=timeout)
```

## Key Configuration Defaults

| Setting | Default | Impact |
|---------|---------|--------|
| `tool_timeout` | 240s (4 min) | Max block time per tool call |
| `default_max_tool_answer_chars` | 150,000 | Max response size before truncation |
| Language server timeout | `tool_timeout - 5s` (235s) | LSP request timeout |

## Recommended Mitigations

### Immediate (User-Side)

1. **Explicit `max_answer_chars`:** Pass `max_answer_chars=50000` on large files to prevent context flooding
2. **Limit depth:** Avoid `depth > 1` on large files (use `depth=0` then targeted `find_symbol`)
3. **Lower timeout:** Set `tool_timeout: 60` in `serena_config.yml` to fail faster
4. **Avoid large files:** Use `find_symbol` or `search_for_pattern` instead for files known to be large

### Upstream (Plugin Fixes)

1. **Stop hook should distinguish tool-output overflow from incomplete work** — `max_tokens` caused by a 150K tool response is not "work in progress"
2. **Task cancellation on timeout** — currently the task keeps running after timeout, consuming resources
3. **Adaptive response size** — scale `max_answer_chars` based on remaining context window, not a fixed 150K
4. **Streaming/pagination** — return symbols in pages instead of one monolithic JSON blob

## Reproduction Triggers

- Call `get_symbols_overview` on a large PHP file (500+ lines, many functions) with `depth=1`
- Call it on a TypeScript file with many exported symbols
- Call it while language server is still indexing after project open
- Call it in rapid succession on multiple files (queue stacking)
