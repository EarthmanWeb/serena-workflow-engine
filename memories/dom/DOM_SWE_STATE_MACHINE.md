---
name: DOM_SWE_STATE_MACHINE
description: State-transition logic for the 12-state workflow FSM plus the WF_INIT entry pseudo-state.
obligations:
  - NEVER `set_state` to a subflow (WF_INIT, WF_CLEANUP, WF_RESEARCH_LITE, WF_UPDATE_MEMORY) — they are documented procedures, not FSM states.
  - NEVER Edit/Write outside WF_EXECUTE, WF_CHECKPOINT, WF_DEBUG_TDD, WF_VERIFY, or WF_ONBOARD.
metadata:
  type: domain
---

# DOM_SWE_STATE_MACHINE — State Transition Logic

## Transition Model (readAdvance + readBackward)

- `readAdvance` (top-level flag in `states.json`) is ENABLED: reading a `WF_*` memory whose per-state `rank` is HIGHER than the current state's `rank` advances the FSM along a valid `transitionMatrix` edge.
- `readBackward` (per-state allowlist in `states.json`) permits a LOWER-rank read to also transition: a read into a state listed in `readBackward[current]` advances the FSM. Entries: `WF_RESEARCH→[WF_CLASSIFY]`, `WF_ARCH_REVIEW→[WF_CLASSIFY]`, `WF_EXECUTE→[WF_CLASSIFY]`, `WF_CHECKPOINT→[WF_CLASSIFY]`, `WF_DEBUG_TDD→[WF_CLASSIFY]`, `WF_VERIFY→[WF_EXECUTE, WF_CLASSIFY]`, `WF_CONTINUE→[WF_CLASSIFY]`. `WF_DONE` has no `readBackward` entries — the prompt hook owns post-completion re-entry.
- Any backward or same-rank read NOT listed in `readBackward[current]` NEVER transitions. `WF_CLARIFY` is NEVER a read-advance/read-backward target — it is a gate the model enters deliberately. Subflow reads NEVER transition.
- `validate-graph.py` enforces `readBackward ⊆ declared transitions` — every `readBackward` target must also be a real edge from that state.
- `subflows` are documented procedures, NOT FSM states: `WF_INIT`, `WF_CLEANUP`, `WF_RESEARCH_LITE`, `WF_UPDATE_MEMORY`. Reading one never advances the FSM and `set_state` must never target one.
- Pivot edges exist from every active state → `WF_CLASSIFY`, plus `SessionStart` → `WF_CONTINUE` and `WF_CLASSIFY` → `WF_ONBOARD`.
- `loopCaps` bound repeated back-and-forth: `WF_EXECUTE` ↔ `WF_CHECKPOINT` (20), `WF_ARCH_REVIEW` self-loop (3), `WF_VERIFY` → `WF_EXECUTE` (3), `WF_CLASSIFY` → `WF_CLARIFY` (3). Exceeding a cap refuses the transition with an escape message; A→B→A→B oscillation warns without refusing.
- Second-or-later "inspecting — no transition" read of the SAME `WF_*` memory (no `readAdvance`/`readBackward` edge applies) emits a LOOP GUARD message naming the exact fallback: `mcp__plugin_swe_swe-wm__swe_wm_transition(session_id, target_state, reason)` (MCP) or `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/swe_hooks/tools/set_state.py" <session_id> <STATE>` (CLI).

## Explicit Transition Tools

- `mcp__plugin_swe_swe-wm__swe_wm_transition(session_id, target_state, reason, force=false)` — the ONLY MCP way to change Current State. Validates against `states.json` (matrix, subflows rejected, `WF_CLARIFY` return rules, loop caps unless `force=true`), writes `.serena/swe-state/<id>.state` + WM Transitions line + a stream state event, returns the new state.
- CLI: `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/swe_hooks/tools/set_state.py" <session_id> <STATE> [--force]` — shares the same core (`state_manager.perform_transition`) as the MCP tool. JSON output; exit 1 on failure. Session id = the 8-char id printed in every hook message (`WM[<id>]` / `session="<id>"`, also the WM filename `WM_<id>.md`). `${CLAUDE_PLUGIN_ROOT}` is set by the plugin system; in this dev repo the plugin root is the repo root.
- `--force`/`force=true` skips matrix-edge/loop-cap validation ONLY — subflow targets are rejected even with `--force`.

## Transition Side-Effects (WF_CLASSIFY entry)

Single choke point: `StateManager.transition_to` — reached by the prompt hook (pivot, WF_DONE → new task), read-advance/readBackward (`swe_post_read_state.py`), and `perform_transition` (`swe_wm_transition` MCP + `set_state.py` CLI).

- Every entry into `WF_CLASSIFY` clears the per-task sweep sentinel (`clear_sweep_sentinel`).
- Entry from a LATER state (`resets_blanket_consent`: `states.json` rank ≥ WF_CLASSIFY's rank — WF_CONTINUE, WF_RESEARCH, WF_ARCH_REVIEW, WF_EXECUTE, WF_CHECKPOINT, WF_DEBUG_TDD, WF_VERIFY, WF_DONE) clears the WM blanket-consent flag via `session.clear_blanket_consent` and logs a `consent_reset` stream event. Applies to forced transitions too.
- The SAME `resets_blanket_consent(old, new)` guard also clears the session's edit-mode sentinel (`core.stream.set_edit_mode(session_id, False)`) — see `mem:dom/DOM_SWE_HOOKS_PROMPT_ROUTING` Edit Mode. One call site, both flags; no separate gap for a model-driven pivot via `swe_wm_transition`/`set_state.py`.
- WF_CLARIFY return, WF_ONBOARD return, and the initial WF_INIT entry NEVER reset consent — same-task detours.

## State Set (v5)

FSM = 12 state nodes in `states.json` PLUS the `WF_INIT` entry pseudo-state and 4 non-FSM subflows.

FSM states: WF_INIT (pseudo-state) · WF_INITIAL_SETUP · WF_ONBOARD · WF_CLASSIFY · WF_CONTINUE · WF_RESEARCH · WF_ARCH_REVIEW · WF_CLARIFY · WF_EXECUTE · WF_CHECKPOINT · WF_DEBUG_TDD · WF_VERIFY · WF_DONE

Subflows (not FSM states, never `set_state` targets): WF_INIT · WF_CLEANUP · WF_RESEARCH_LITE · WF_UPDATE_MEMORY

## State Roles

| State          | Category             | Role                                                                   |
| -------------- | -------------------- | ---------------------------------------------------------------------- |
| WF_INIT        | Entry                | Init pseudo-state; chain ends by routing to WF_CLASSIFY                |
| WF_CLASSIFY    | Entry                | Post-init entry; route by complexity (simple/medium/large/operational) |
| WF_CONTINUE    | Entry                | Resume from WORKING_MEMORY                                             |
| WF_RESEARCH    | Analysis             | Read-only exploration                                                  |
| WF_ARCH_REVIEW | Planning (Plan Mode) | Design, compliance review, parallel-subagent assessment & approval     |
| WF_CLARIFY     | Gate                 | Ask user questions                                                     |
| WF_EXECUTE     | Execution            | Make changes (allows Edit/Write)                                       |
| WF_CHECKPOINT  | Execution            | Save progress every 10 edits (`CHECKPOINT_THRESHOLD`)                  |
| WF_DEBUG_TDD   | Execution            | Test-driven debugging                                                  |
| WF_VERIFY      | Completion           | Test and validate                                                      |
| WF_DONE        | Completion           | Record reusable learnings in WM (mandatory)                            |

## Complexity Routing (WF_CLASSIFY)

| Complexity | Files | Layers | Route To                                         |
| ---------- | ----- | ------ | ------------------------------------------------ |
| All        | Any   | Any    | WF_ARCH_REVIEW (code) / WF_EXECUTE (operational) |

- Run the parallel-subagent assessment at WF_ARCH_REVIEW AFTER feature context is loaded. NEVER assess before feature context loads.

## Plan Mode Triggers

- ALWAYS Plan Mode: WF_ARCH_REVIEW.
- NEVER Plan Mode: WF_DEBUG_TDD, WF_VERIFY, WF_DONE, WF_EXECUTE.
- Conditional Plan Mode: WF_CLASSIFY (medium+).

## Edit Permissions

| State         | Edit | Write |
| ------------- | ---- | ----- |
| WF_EXECUTE    | ✓    | ✓     |
| WF_CHECKPOINT | ✓    | ✓     |
| WF_DEBUG_TDD  | ✓    | ✓     |
| WF_VERIFY     | ✓    | ✓     |
| WF_ONBOARD    | ✓    | ✓     |
| Others        | ✗    | ✗     |

- NEVER Edit/Write in any state marked ✗.

## Critical Paths

- Happy Path: WF_INIT → WF_CLASSIFY → WF_ARCH_REVIEW → WF_EXECUTE → WF_VERIFY → WF_DONE
- Debug Path: WF_CLASSIFY → WF_DEBUG_TDD → WF_EXECUTE → WF_VERIFY → WF_DONE
- Large Task (parallel subagents): WF_CLASSIFY → WF_ARCH_REVIEW → WF_EXECUTE (launches subagents) → WF_VERIFY → WF_DONE
- Pivot (any active state): active state → WF_CLASSIFY (re-classify on a genuine new task or full pivot; see `mem:dom/DOM_SWE_HOOKS_PROMPT_ROUTING` for when this fires)
- Resume: SessionStart → WF_CONTINUE
- Feature setup mid-task: WF_CLASSIFY → WF_ONBOARD → WF_CLASSIFY
