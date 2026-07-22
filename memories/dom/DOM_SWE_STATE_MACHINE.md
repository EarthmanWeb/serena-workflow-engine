---
name: DOM_SWE_STATE_MACHINE
description: State-transition logic for the 13-state workflow FSM plus the WF_INIT entry pseudo-state.
metadata:
  type: domain
---

# DOM_SWE_STATE_MACHINE — State Transition Logic

## Transition Model

- Reading a `WF_*` memory is a PURE read. It displays/logs the step ONLY. It NEVER advances the FSM.
- Transition state via `set_state` ONLY (the dedicated tool OR the prompt-intent hook). NEVER treat a read as a transition.

## State Set (v4)

FSM = 13 state nodes in `states.json` PLUS the `WF_INIT` entry pseudo-state.

WF_INIT (pseudo-state) · WF_INITIAL_SETUP · WF_ONBOARD · WF_CLASSIFY · WF_CONTINUE · WF_RESEARCH · WF_RESEARCH_LITE · WF_ARCH_REVIEW · WF_SWARM_ORCHESTRATE · WF_CLARIFY · WF_EXECUTE · WF_CHECKPOINT · WF_DEBUG_TDD · WF_VERIFY · WF_DONE

## State Roles

| State | Category | Role |
| ----- | -------- | ---- |
| WF_INIT | Entry | Init pseudo-state; chain ends by routing to WF_CLASSIFY |
| WF_CLASSIFY | Entry | Post-init entry; route by complexity (simple/medium/large/operational) |
| WF_CONTINUE | Entry | Resume from WORKING_MEMORY |
| WF_RESEARCH | Analysis | Read-only exploration |
| WF_RESEARCH_LITE | Analysis | Lightweight read-only exploration |
| WF_ARCH_REVIEW | Planning (Plan Mode) | Design, compliance review, swarm assessment & approval |
| WF_SWARM_ORCHESTRATE | Planning (Plan Mode) | Multi-agent coordination |
| WF_CLARIFY | Gate | Ask user questions (penalty in RLVR) |
| WF_EXECUTE | Execution | Make changes (allows Edit/Write) |
| WF_CHECKPOINT | Execution | Save progress every 3 edits |
| WF_DEBUG_TDD | Execution | Test-driven debugging |
| WF_VERIFY | Completion | Test and validate |
| WF_DONE | Completion | RLVR learning (mandatory) |

## Complexity Routing (WF_CLASSIFY)

| Complexity | Files | Layers | Route To |
| ---------- | ----- | ------ | -------- |
| All | Any | Any | WF_ARCH_REVIEW (code) / WF_EXECUTE (operational) |

- Run swarm assessment at WF_ARCH_REVIEW AFTER feature context is loaded. NEVER assess swarm before feature context loads.

## Plan Mode Triggers

- ALWAYS Plan Mode: WF_ARCH_REVIEW, WF_SWARM_ORCHESTRATE.
- NEVER Plan Mode: WF_DEBUG_TDD, WF_VERIFY, WF_DONE, WF_EXECUTE.
- Conditional Plan Mode: WF_CLASSIFY (medium+).

## Edit Permissions

| State | Edit | Write |
| ----- | ---- | ----- |
| WF_EXECUTE | ✓ | ✓ |
| WF_CHECKPOINT | ✓ | ✓ |
| WF_DEBUG_TDD | ✓ | ✓ |
| WF_VERIFY | ✓ | ✓ |
| WF_ONBOARD | ✓ | ✓ |
| Others | ✗ | ✗ |

- NEVER Edit/Write in any state marked ✗.

## Critical Paths

- Happy Path: WF_INIT → WF_CLASSIFY → WF_ARCH_REVIEW → WF_EXECUTE → WF_VERIFY → WF_DONE
- Debug Path: WF_CLASSIFY → WF_DEBUG_TDD → WF_EXECUTE → WF_VERIFY → WF_DONE
- Large Task: WF_CLASSIFY → WF_ARCH_REVIEW → WF_SWARM_ORCHESTRATE → WF_EXECUTE → WF_VERIFY → WF_DONE
- Onboard → Swarm: WF_INIT → WF_ONBOARD (DAA analysis) → WF_SWARM_ORCHESTRATE → WF_EXECUTE → WF_VERIFY → WF_DONE
