---
name: DOM_SWE_HOOKS_PRE_GATES_INIT_FS
description: PreToolUse init gate (two-tier circuit breaker + sentinel recovery) and memory-fs gate — tool unlocks, hardened Bash classifier, spawned-agent exemptions.
metadata:
  type: domain
obligations:
  - Init gate blocks ALL tools until the WF_INIT chain completes; Tier-1/Tier-2 degraded modes never unlock Edit/Write/NotebookEdit/mutating Bash; exempt for spawned-agent tool calls.
  - Init gate enforces `[scope-gate]` per spawned agent (test 2/edit 2/bash 3 failure streaks, tool-call budget; `test` limit widens by `EXPECT_RED_TEST_BONUS` (2) when the agent was spawned with `expect_red`); a trip restricts the agent to read-only tools until the orchestrator sends `[scope-extend]`.
  - `swe_pre_memory_fs_gate.py` DENIES Bash/Grep/Glob/Read access to Serena memory stores (`.serena/memory/`, `.serena/memories/`, the auto-memory symlink) for BOTH main agent and subagents — shell reads and shell content writes alike; exempt only for uninitialized/bypassed projects and the spawned `swe-init-agent`.
---

# DOM_SWE_HOOKS_PRE_GATES_INIT_FS — Init Gate + Memory-FS Gate

Hub: `mem:dom/DOM_SWE_HOOKS_PRE_GATES`.

## `swe_pre_memory_fs_gate.py` — PreToolUse (Bash/Grep/Glob/Read)

Shared classifier: `hooks/swe_hooks/core/memory_fs.py` (`is_memory_store_path`, `bash_memory_access`, `tool_memory_access`).

- DENIES Bash/Grep/Glob/Read access to Serena memory STORES: `.serena/memory/`, `.serena/memories/`, and the `~/.claude/projects/<enc>/memory` auto-memory symlink — resolved via realpath so the symlink target is caught even when addressed through the link.
- Applies to BOTH the main agent AND subagents — no subagent-type exemption except the spawned `swe-init-agent` (`agent_type` check).
- Denies shell READS (cat/grep/rg/awk/sed/head/tail/ls/find/wc, Read/Grep/Glob tool calls) AND shell CONTENT WRITES into a memory path: redirection into a memory file, `tee`, `sed -i`, `perl -i`, an inline `python -c`/`node -e`/heredoc that touches a memory path.
- Exempt (NOT gated): project not initialized or bypassed (`core.config.resolve_setup_state` → `initialized` false, or `"bypass": true` in `swe-setup-complete.json`); `git`, `mkdir`, `ln`, `cp`, `mv`, `rm` targeting memory paths; running a script FILE (`python3 scripts/... --root .serena/memory`) — the gate inspects inline code, not script invocations; grepping plugin-SOURCE files for the literal string `.serena/memory` (text search over non-memory trees); `WM_*.md` session files; the plugin-source `memories/` tree of the plugin repo (not a Serena memory store — edited as plain files).
- Deny message routes each blocked intent to the Serena memory tool that replaces it: a name/keyword lookup → `read_memory`/`list_memories`/`search_memories_by_name`; a "what is this about" lookup → `search_memories_by_front_matter`; a body/content search → `mcp__plugin_swe_serena__search_for_pattern(substring_pattern=…, relative_path=".serena/memory")`; a write → `write_memory`/`edit_memory`; a WM read → `swe_wm_read`.
- `swe_pre_edit_validate.py`'s `_is_raw_memory_write` check now calls `memory_fs.is_memory_store_path` — symlink-aware, same resolution as this gate.
- `swe_pre_search_docs_gate.py` B2 credits a "memory-grep" docread ONLY for plugin-source `memories/` path segments — memory-STORE access passes through this gate with no `docread` event (denied here when gated, allowed through uncredited when exempt).
- Registered in `hooks/hooks.json` as matcher `Bash|Grep|Glob|Read`, directly after the init gate.

## `swe_pre_tool_init_gate.py` — PreToolUse (all tools)

Block ALL tools until WF_INIT chain complete. TWO-TIER circuit breaker, both clearing on the next docread.

- **Tier 1 "recovery"** (3+ consecutive init denies with no docread, no `mcp_unavailable`): Serena may still be reachable — unlocks ONLY recovery/diagnostic Bash: `claude mcp list`/`get`, `ps`/`pgrep`, restricted log reads under `~/Library/Caches/claude-cli-nodejs/`, `~/.cache/claude-cli-nodejs/`, `~/.serena/logs/`, project `.serena/`, plus `--reset-sentinel`. NEVER Read/Grep/Glob the codebase.
- **Tier 2 "degraded"** (an `mcp_unavailable` event from `PostToolUseFailure` on a genuine Serena connection failure): unlocks Read/Grep/Glob/LS/ToolSearch + hardened read-only Bash.
- Edits/Write/NotebookEdit/mutating Bash stay denied in BOTH tiers.
- Hardened Bash classifier rejects: backtick/`$()`/`<()`/`>()`/redirection (except `2>/dev/null`, `2>&1`)/`tee`/`xargs`/`-exec`/`-execdir`/`-delete`/`sed -i`/`perl -i`. Every `;`/`&&`/`||`/`&`/pipe-stage's primary command must be in the allowlist. Excludes `python3 -m unittest`/`pytest` (execute code). git limited to `status`/`log`/`diff`/`show`/`branch`/`rev-parse` without `-c`/`--output`/`-o`.
- Events emitted: `init_deny`, `degraded`, `mcp_unavailable`.
- Allowed pre-init: `read_memory` (wf/* and init-chain), `write_memory`, `edit_memory`, `list_memories`, swe_wm tools, `ToolSearch`, Serena project-setup tools.
- Blocked pre-init: `Bash`, `Grep`, `Glob`, `Edit`, `Write` (non-WM), `find_symbol`, `get_symbols_overview`, all other tools.
- Sentinel on entry to WF_CLASSIFY unlocks all tools for the session.
- Spawned agents: also enforces the `[scope-gate]` verdict from `hooks/swe_hooks/core/scope_guard.py` — a tripped agent (consecutive failure streak by kind: test 2, edit 2, bash 3; or tool-call budget exhausted) gets ONLY read-only tools (Read/Grep/Glob/Serena reads/memory reads/SendMessage); every spawned-agent tool call logs an `agent_call` event for streak/budget tracking.

### Sentinel Recovery (self-healing)

Recreate a missing sentinel automatically when a valid WM exists for the session — prevents deadlock on mid-session pivots where the daemon blocks re-running the init chain but the gate demands it.

Recovery points, checked in order:

1. `swe_user_prompt_workflow.py` — create sentinel when WM valid but sentinel missing, before any tool call.
2. `swe_pre_tool_init_gate.py` — WM-based fallback when the prompt hook did not fire or failed.

### Manual Reset

- One session: `python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel <session_id>`.
- ALL sentinels (next init chain recreates them): `python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel`.

## Spawned-agent exemptions vs per-agent gating

- `swe_pre_tool_init_gate.py`: exempt for spawned-agent tool calls — a subagent bypasses the init chain entirely per its prompt marker, not per this gate; the bypass guard (marker detection) and Serena session metadata (`agent_id`/`agent_type`) still apply to identify the call as spawned.
- `swe_pre_bash_test_gate.py`: EXEMPT for spawned-agent Bash calls — per-agent TEST-doc gating is REMOVED; a subagent's TEST-doc requirement is enforced once, at delegation time, by `[sweep-gate]` (`mem:dom/DOM_SWE_HOOKS_PRE_GATES_AGENT`).
- `swe_pre_edit_validate.py`: EXEMPT for spawned-agent edits — `[doc-gate]` is now MAIN-AGENT-ONLY; a subagent's `doc_requirements` are enforced once, at delegation time, by `[sweep-gate]` (`mem:dom/DOM_SWE_HOOKS_PRE_GATES_AGENT`), not per edit inside the subagent's own run. The drift-block/sweep-sentinel checks in this gate remain main-agent-only as before.
- `swe_pre_agent_model_gate.py`: applies ONLY to the orchestrator's Agent/Task call, never to a spawned agent's own tool calls — `[sweep-gate]` is where subagent doc/test-reading enforcement now lives, entirely at spawn time.
- `swe_pre_memory_fs_gate.py`: NOT exempt for subagents — applies to every spawned agent's Bash/Grep/Glob/Read calls same as the main agent. The ONLY agent-type exemption is the spawned `swe-init-agent` (bootstrap needs direct memory-path access before the Serena memory store exists).
