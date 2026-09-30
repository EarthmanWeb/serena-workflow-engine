---
name: swe-goto
description: Force transition to specific state (debug/recovery)
argument-hint: [STATE]
---

# /swe-goto [STATE]

Force transition to a specific workflow state.

## Usage

```
/swe-goto WF_EXECUTE
/swe-goto WF_CHECKPOINT
```

## Warning

This bypasses matrix/loop-cap validation. Use only for debugging or recovery. Subflows (`WF_INIT`, `WF_CLEANUP`, `WF_RESEARCH_LITE`, `WF_UPDATE_MEMORY`) are REJECTED even with `--force` — they are documented procedures, never `set_state` targets.

## Steps

1. Resolve the session id — the 8-char id printed in every hook message (`WM[<id>]` / `session="<id>"`), also the WM filename `WM_<id>.md`.
2. PREFERRED — call the MCP tool:
   ```
   mcp__plugin_swe_swe-wm__swe_wm_transition(session_id="<id>", target_state="<STATE>", reason="<why>", force=<bool>)
   ```
   CLI equivalent (same shared core, `state_manager.perform_transition`):
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/swe_hooks/tools/set_state.py" <session_id> <STATE> [--force]
   ```
   JSON output; exits 1 on failure. `CLAUDE_PLUGIN_ROOT` is set by the plugin system for commands/hooks; in this dev repo the plugin root is the repo root.
3. On success, read the target state's memory: `mcp__plugin_swe_serena__read_memory(memory_name="wf/<STATE>")`.
4. Report: `> **On step <STATE>** (forced)` when `force=true` was used.

`--force`/`force=true` skips matrix-edge and loop-cap validation ONLY — it never permits a subflow target.
