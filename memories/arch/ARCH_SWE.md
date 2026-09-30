---
name: ARCH_SWE
description: Workflow system architecture — FSM over Serena memories, state format, routing layers, integration points, modification checklist, and dependencies.
metadata:
  type: architecture
---

# ARCH_SWE — Workflow System Architecture

The workflow system is a finite state machine over Serena memories. Each `WF_*` memory is a self-contained instruction set Claude reads and executes sequentially. See `mem:claude/CLAUDE_META` for the memory-type reference, step-reporting contract, and rules for adding/modifying states.

## Core Principles

- Read exactly ONE `WF_*` memory at a time. Execute its steps, then transition. NEVER read multiple `WF_*` memories concurrently.
- Every `WF_*` memory declares its transitions in a `## Routing` table. Skipping a transition = workflow violation.
- Output the step-report line immediately on entering a state: `> **On step WF_[NAME]**`.
- WM (Working Memory) provides session continuity across turns and enables `WF_CONTINUE` to resume work.

### Read-Advance (v5)

- `readAdvance` in `state-machine/states.json` is enabled: reading a `WF_*` memory whose per-state `rank` is HIGHER than the current state's rank advances the FSM along a valid `transitionMatrix` edge. Backward reads, same-rank reads, and reads into `WF_CLARIFY` NEVER transition.
- `subflows` (`WF_INIT`, `WF_CLEANUP`, `WF_RESEARCH_LITE`, `WF_UPDATE_MEMORY`) are documented procedures, NOT FSM states — never `set_state` to them.
- Pivot edges exist from every active state → `WF_CLASSIFY`; `SessionStart` → `WF_CONTINUE`; `WF_CLASSIFY` → `WF_ONBOARD`.
- `loopCaps` bound repeated transitions (e.g. `WF_EXECUTE` ↔ `WF_CHECKPOINT` capped at 20, `WF_ARCH_REVIEW` self-loop capped at 3, `WF_VERIFY` → `WF_EXECUTE` capped at 3, `WF_CLASSIFY` → `WF_CLARIFY` capped at 3). Exceeding a cap refuses the transition with an escape message; A→B→A→B oscillation warns. See `mem:dom/DOM_SWE_STATE_MACHINE`.

## Routing Layers

| Layer      | States                                                                |
| ---------- | --------------------------------------------------------------------- |
| Entry      | `WF_INIT` → `WF_CLASSIFY` → routing decision                          |
| Research   | `WF_RESEARCH`                                                         |
| Code tasks | routed via `WF_CLASSIFY`                                              |
| Review     | `WF_ARCH_REVIEW` (design + compliance + parallel-subagent assessment) |
| Gate       | `WF_ARCH_REVIEW` (includes approval) ←→ `WF_CLARIFY`                  |
| Execution  | `WF_EXECUTE` ←→ `WF_CHECKPOINT` ←→ `WF_DEBUG_TDD`                     |
| Completion | `WF_VERIFY` → `WF_DONE`                                               |

## Integration Points

### Skill Integration (WCP/SRP)

- Calling state sets `## Workflow Context` in WM.
- Skill executes and writes `## Skill Return`.
- Calling state reads return status and routes accordingly.
- Ref: `mem:ref/REF_WM` (Skill Return section, status codes).

### Subagent Integration

- Parallel work uses Claude Code's built-in `Agent` tool (subagents), launched inside `WF_EXECUTE`.
- Each subagent runs in its own context window; use `isolation: "worktree"` when subagents edit overlapping files.
- Aggregate results back to the main workflow.
- Ref: `mem:feature/FEATURE_SUBAGENTS`.

### Memory Integration

- `MEMORY.md` — navigation (auto-loaded by Claude Code).
- `feature/FEATURE_*` — scope.
- `dom/DOM_*` — domain context.
- `arch/ARCH_*` — architecture patterns.
- `index/INDEX_*` — file/symbol lookup.

## State Memory Format

Every `WF_*` memory follows this structure:

```markdown
---
name: WF_[NAME]
description: <one sentence>
metadata:
  type: workflow
---

# WF_[NAME] — [Description]

> **On step WF_[NAME]**

[Numbered/sectioned steps with specific actions]

## Routing

| Condition   | Next Step   |
| ----------- | ----------- |
| [condition] | `WF_[NEXT]` |

Update WM via `/swe-wm-update` before transitioning.
```

Output the step-report line (`> **On step WF_[NAME]**`) immediately on entering the state. Every state declares its transitions in a `## Routing` table — do NOT leave the next state implicit.

## Modification Checklist

When modifying the workflow system:

- [ ] Identify all affected states.
- [ ] Update `WF_*` memory content and its `## Routing` table.
- [ ] Update `state-machine/states.json` (transitions, `transitionMatrix`, `rank`, `loopCaps` as applicable).
- [ ] Run `python3 scripts/validate-graph.py`.
- [ ] Run `python3 scripts/validate-memory-graph.py`.
- [ ] Update `dom/DOM_SWE_STATE_MACHINE` (state set, transition model, critical paths).
- [ ] Test affected paths manually.

## Dependencies

| Component        | Depends On                                                                                |
| ---------------- | ----------------------------------------------------------------------------------------- |
| `WF_CLASSIFY`    | `claude/CLAUDE_OBLIGATIONS`, `index/INDEX_FEATURES`, WM, `MEMORY.md`, `feature/FEATURE_*` |
| `WF_CLASSIFY`    | (also) `dom/DOM_*`, `ref/REF_*`                                                           |
| `WF_ARCH_REVIEW` | `feature/FEATURE_DEV_STANDARDS`, `dev/DEV_*`, `dom/DOM_*`, `ref/REF_*`                    |
| `WF_VERIFY`      | `claude/CLAUDE_OBLIGATIONS`, `feature/FEATURE_DEV_STANDARDS`                              |
| Skills           | `ref/REF_WM`, WM                                                                          |
