---
name: DOM_SWE_STATE_MACHINE
description: State-transition logic for the 12-state workflow FSM plus the WF_INIT entry pseudo-state.
metadata:
  type: domain
---

# DOM_SWE_STATE_MACHINE — State Transition Logic

## Transition Model (readAdvance)

- `readAdvance` (top-level flag in `states.json`) is ENABLED: reading a `WF_*` memory whose per-state `rank` is HIGHER than the current state's `rank` advances the FSM along a valid `transitionMatrix` edge.
- Backward reads (lower or equal `rank`) and any read into `WF_CLARIFY` NEVER transition — `WF_CLARIFY` is a gate the model enters deliberately, not by read-advance.
- `subflows` are documented procedures, NOT FSM states: `WF_INIT`, `WF_CLEANUP`, `WF_RESEARCH_LITE`, `WF_UPDATE_MEMORY`. Reading one never advances the FSM and `set_state` must never target one.
- Pivot edges exist from every active state → `WF_CLASSIFY`, plus `SessionStart` → `WF_CONTINUE` and `WF_CLASSIFY` → `WF_ONBOARD`.
- `loopCaps` bound repeated back-and-forth: `WF_EXECUTE` ↔ `WF_CHECKPOINT` (20), `WF_ARCH_REVIEW` self-loop (3), `WF_VERIFY` → `WF_EXECUTE` (3), `WF_CLASSIFY` → `WF_CLARIFY` (3). Exceeding a cap refuses the transition with an escape message; A→B→A→B oscillation warns without refusing.

## State Set (v4)

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
- Pivot (any active state): active state → WF_CLASSIFY (re-classify on a genuine new task or full pivot; see `mem:dom/DOM_SWE_HOOKS` prompt-intent routing for when this fires)
- Resume: SessionStart → WF_CONTINUE
- Feature setup mid-task: WF_CLASSIFY → WF_ONBOARD → WF_CLASSIFY
