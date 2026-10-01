---
name: DOM_SWE_HOOKS
description: Python hook architecture hub — output contract, package layout, hook inventory, and a routing table to the split-out detail memories (pre-gates, post-observers, prompt routing, stop, core modules).
obligations:
  - Hooks MUST write JSON to STDOUT only, NEVER stderr, and MUST always exit 0 — NEVER exit 1.
  - Store workflow state in the session's WM `## Workflow Context` section, NEVER a global state file.
metadata:
  type: domain
---

# DOM_SWE_HOOKS — Python Hook Architecture (Hub)

This memory is the hub for the `dom/DOM_SWE_HOOKS_*` family. Read the invariants below on every open; open a child ONLY for the topic you need — see the routing table.

## Output Contract

- Write JSON to STDOUT. NEVER write to stderr.
- Exit code MUST be 0 always. NEVER exit 1.
- Emit user-visible text via `hookSpecificOutput.additionalContext`.
- Block operations via `hookSpecificOutput.permissionDecision = "deny"` (PreToolUse only).
- All hooks are Python 3, following the Anthropic `hookify` plugin pattern.
- Full JSON examples + HookOutput/StateManager/Session/WM-Validator/Orphan-Reaper API: `mem:dom/DOM_SWE_HOOKS_CORE_MODULES`.

## Package Structure

```
hooks/
├── swe_hooks/
│   ├── __init__.py
│   ├── bootstrap.py              # Import fallback, path setup
│   ├── core/
│   │   ├── output.py             # HookOutput class, helpers
│   │   ├── input.py              # Input parsing helpers
│   │   ├── config.py             # Path helpers, state loading
│   │   ├── session.py            # Session ID, WM management
│   │   ├── state_manager.py      # State machine logic
│   │   ├── stream.py             # Append-only JSONL event log
│   │   ├── orphan_reaper.py      # Kills orphaned VS-Code-extension Claude sessions (ppid==1)
│   │   ├── memory_fs.py          # Memory-store path/Bash classifier (symlink-aware)
│   │   └── wm_validator.py       # Working Memory validation
│   ├── mcp/
│   │   └── wm_server.py          # swe-wm MCP server
│   └── tools/
│       └── set_state.py          # State manipulation utility
├── session/ prompt/ pre/ post/ stop/
└── hooks.json
```

## Hook Inventory (21 scripts) — condensed

### Session (`session/`)

| Hook                   | Event        | Purpose                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ---------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `swe_session_start.py` | SessionStart | Initialize workflow state, auto-update. Appends `session_boot` (with `src`: startup/resume/clear/compact) BEFORE the self-update and `selfupdate` (ok/old/new or err) after it — a `session_boot` with no following `selfupdate` = update killed by the hook timeout (30s). Also reaps outdated-version daemons AND orphaned VS-Code-extension Claude sessions (see `mem:dom/DOM_SWE_HOOKS_CORE_MODULES` Orphan Reaper) — both best-effort, never block boot |
| `swe_session_end.py`   | SessionEnd   | Clean up sentinels, mark WM abandoned                                                                                                                                                                                                                                                                                                                                                                                                                        |

### Prompt (`prompt/`)

| Hook                            | Event            | Purpose                                                                                                                                                                             |
| ------------------------------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `swe_user_prompt_workflow.py`   | UserPromptSubmit | WF_INIT gate, intent analysis, state transitions — full detail in `mem:dom/DOM_SWE_HOOKS_PROMPT_ROUTING`                                                                            |
| `swe_prompt_format_reminder.py` | UserPromptSubmit | Pre-emptive format-budget reminder: when `swe_stop_response_format.py` blocked the prior turn, surface the budget on the next turn + clear the sentinel. Same enabled/bypass guards |

### Pre-Tool (`pre/`) — gatekeepers

8 hooks: init gate (two-tier circuit breaker), memory-fs gate, edit validate, memory index gate, bash test gate, docs-first search gate, question consent gate, agent model gate. Full detail: `mem:dom/DOM_SWE_HOOKS_PRE_GATES`.

### Post-Tool (`post/`) — observers/learners

9 hooks: read-state (readAdvance), edit checkpoint, search-docs hint, write-continue, todo-wm-sync, memory-index, memory-style, tool-failure, doc-claims, orchestrator-drift. Full detail: `mem:dom/DOM_SWE_HOOKS_POST`; sentinel mechanism: `mem:dom/DOM_SWE_HOOKS_SENTINELS`.

### Stop (`stop/`)

2 hooks: continue-working, response-format gate. Full detail: `mem:dom/DOM_SWE_HOOKS_STOP`.

## Routing Table

| When                                                                                                                                                                               | Read                                   |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| Debugging/editing a PreToolUse gate (init gate, memory-fs gate, edit validate, memory index gate, bash test gate, docs-first search gate, question consent gate, agent model gate) | `mem:dom/DOM_SWE_HOOKS_PRE_GATES`      |
| Debugging/editing a PostToolUse observer                                                                                                                                           | `mem:dom/DOM_SWE_HOOKS_POST`           |
| Debugging/editing the sentinel nudge mechanism (checkpoint/search-hint/drift thresholds)                                                                                           | `mem:dom/DOM_SWE_HOOKS_SENTINELS`      |
| Debugging/editing prompt-intent classification, pivot detection, session-reset, or task-boundary/sweep stamping                                                                    | `mem:dom/DOM_SWE_HOOKS_PROMPT_ROUTING` |
| Debugging/editing a Stop hook (continue-working, terse-response-format gate)                                                                                                       | `mem:dom/DOM_SWE_HOOKS_STOP`           |
| Writing/reading hook output JSON, using HookOutput/StateManager/Session/WM-Validator/Orphan-Reaper, verifying hook loading, or running the diagnostic checklist                    | `mem:dom/DOM_SWE_HOOKS_CORE_MODULES`   |
| Understanding `readAdvance` state transitions                                                                                                                                      | `mem:dom/DOM_SWE_STATE_MACHINE`        |

## Instruction File Strategy

- Hooks NEVER read and echo instruction-file contents.
- Hooks point the agent to `mcp__plugin_swe_serena__read_memory("wf/WF_*")`.
- Instruction files are copied to `.serena/swe/` during `/swe-init`.
