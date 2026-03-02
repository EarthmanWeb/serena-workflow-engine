# DOM_SWE_STATE_MACHINE - State Transition Logic

## Purpose

Documents the 21-state workflow FSM and transition rules.

## State Categories

### Entry States

- **WF_START** - Mandatory entry, reads context
- **WF_CLASSIFY** - Routes by complexity (simple/medium/large)
- **WF_CONTINUE** - Resume from WORKING_MEMORY

### Analysis States

- **WF_RESEARCH** - Read-only exploration

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
| WF_UPDATE_MEMORY | ✓    | ✓     |
| WF_ONBOARD       | ✓    | ✓     |
| Others           | ✗    | ✗     |

## Critical Paths

```
Happy Path: START → CLASSIFY → DETECT_REQ → LOAD_FEATURE → ARCH_REVIEW → ASK_PERMISSION → EXECUTE → VERIFY → DONE → CLEANUP

Debug Path: CLASSIFY → DEBUG_TDD → EXECUTE → VERIFY → DONE

Large Task: CLASSIFY → PLAN_ARCHITECTURE → SWARM_ORCHESTRATE → EXECUTE → VERIFY → DONE

Onboard → Swarm: START → ONBOARD (DAA analysis) → SWARM_ORCHESTRATE → EXECUTE → VERIFY → DONE
```
