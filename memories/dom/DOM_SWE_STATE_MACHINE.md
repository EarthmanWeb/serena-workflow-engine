# DOM_SWE_STATE_MACHINE - State Transition Logic

## Purpose

Documents the 13-state workflow FSM (13 state nodes in states.json, plus the WF_INIT entry pseudo-state) and transition rules.

> **Reads do NOT cause transitions.** Reading a `WF_*` memory only displays/logs the
> step — it never advances the FSM. Transitions are **explicit only** (via `set_state`:
> the dedicated tool or the prompt-intent hook).

## State Set (v4)

WF_INIT (pseudo-state) · WF_INITIAL_SETUP · WF_ONBOARD · WF_CLASSIFY · WF_CONTINUE ·
WF_RESEARCH · WF_RESEARCH_LITE · WF_ARCH_REVIEW · WF_SWARM_ORCHESTRATE · WF_CLARIFY ·
WF_EXECUTE · WF_CHECKPOINT · WF_DEBUG_TDD · WF_VERIFY · WF_DONE

## State Categories

### Entry States

- **WF_INIT** - Init pseudo-state; chain ends by routing to WF_CLASSIFY
- **WF_CLASSIFY** - Post-init entry; routes by complexity (simple/medium/large/operational)
- **WF_CONTINUE** - Resume from WORKING_MEMORY

### Analysis States

- **WF_RESEARCH** - Read-only exploration
- **WF_RESEARCH_LITE** - Lightweight read-only exploration

### Planning States (Plan Mode Required)

- **WF_ARCH_REVIEW** - Design, compliance review, swarm assessment & approval
- **WF_SWARM_ORCHESTRATE** - Multi-agent coordination

### Gate States

- **WF_CLARIFY** - Ask user questions (penalty in RLVR)

### Execution States

- **WF_EXECUTE** - Make changes (allows Edit/Write)
- **WF_CHECKPOINT** - Save progress (every 3 edits)
- **WF_DEBUG_TDD** - Test-driven debugging

### Completion States

- **WF_VERIFY** - Test and validate
- **WF_DONE** - RLVR learning (mandatory)

## Transition Rules

### Complexity Routing (WF_CLASSIFY)

| Complexity | Files | Layers | Route To        |
| ---------- | ----- | ------ | --------------- |
| All        | Any   | Any    | WF_ARCH_REVIEW (code) / WF_EXECUTE (operational) |

Swarm assessment happens at WF_ARCH_REVIEW after feature context is loaded.

### Plan Mode Triggers

- **Always**: WF_ARCH_REVIEW, WF_SWARM_ORCHESTRATE
- **Never**: WF_DEBUG_TDD, WF_VERIFY, WF_DONE, WF_EXECUTE
- **Conditional**: WF_CLASSIFY (medium+)

### Edit Permissions

| State            | Edit | Write |
| ---------------- | ---- | ----- |
| WF_EXECUTE       | ✓    | ✓     |
| WF_CHECKPOINT    | ✓    | ✓     |
| WF_DEBUG_TDD     | ✓    | ✓     |
| WF_VERIFY        | ✓    | ✓     |
| WF_ONBOARD       | ✓    | ✓     |
| Others           | ✗    | ✗     |

## Critical Paths

```
Happy Path: WF_INIT → WF_CLASSIFY → WF_ARCH_REVIEW → WF_EXECUTE → WF_VERIFY → WF_DONE

Debug Path: WF_CLASSIFY → WF_DEBUG_TDD → WF_EXECUTE → WF_VERIFY → WF_DONE

Large Task: WF_CLASSIFY → WF_ARCH_REVIEW → WF_SWARM_ORCHESTRATE → WF_EXECUTE → WF_VERIFY → WF_DONE

Onboard → Swarm: WF_INIT → WF_ONBOARD (DAA analysis) → WF_SWARM_ORCHESTRATE → WF_EXECUTE → WF_VERIFY → WF_DONE
```

**Transitions are explicit only.** Reading a `WF_*` memory does not move the FSM —
only `set_state` (dedicated tool / prompt-intent hook) advances the state.
