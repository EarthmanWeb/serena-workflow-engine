---
name: ARCH_SWE
description: Workflow system architecture — FSM over Serena memories, state format, routing layers, integration points, modification checklist, and dependencies.
metadata:
  type: architecture
---

# ARCH_SWE — Workflow System Architecture

The workflow system is a finite state machine over Serena memories. Each `WF_*` memory is a self-contained instruction set Claude reads and executes sequentially.

## Core Principles

- Read exactly ONE `WF_*` memory at a time. Execute its steps, then transition. NEVER read multiple `WF_*` memories concurrently.
- Every `WF_*` memory ends with a "MANDATORY NEXT STEP" section. Skipping a transition = workflow violation.
- Output the step-report line immediately on entering a state: `> **🚀 On step WF_[NAME]**`.
- WM (Working Memory) provides session continuity across turns and enables `WF_CONTINUE` to resume work.

## Routing Layers

| Layer      | States                                                              |
| ---------- | ------------------------------------------------------------------ |
| Entry      | `WF_INIT` → `WF_CLASSIFY` → routing decision                       |
| Research   | `WF_RESEARCH`                                                       |
| Code tasks | routed via `WF_CLASSIFY`                                            |
| Review     | `WF_ARCH_REVIEW` (design + compliance + parallel-subagent assessment) |
| Gate       | `WF_ARCH_REVIEW` (includes approval) ←→ `WF_CLARIFY`               |
| Execution  | `WF_EXECUTE` ←→ `WF_CHECKPOINT` ←→ `WF_DEBUG_TDD`                  |
| Completion | `WF_VERIFY` → `WF_DONE`                                            |

## Integration Points

### Skill Integration (WCP/SRP)

- Calling state sets `## Workflow Context` in WM.
- Skill executes and writes `## Skill Return`.
- Calling state reads return status and routes accordingly.
- Refs: `REF_SKILL_PROTOCOLS`, `SPEC_WORKFLOW_SKILLS`.

### Subagent Integration

- Parallel work uses Claude Code's built-in `Agent` tool (subagents), launched inside `WF_EXECUTE`.
- Each subagent runs in its own context window; use `isolation: "worktree"` when subagents edit overlapping files.
- Aggregate results back to the main workflow.
- Refs: `FEATURE_SUBAGENTS`.

### Memory Integration

- `MEMORY.md` — navigation (auto-loaded by Claude Code).
- `FEATURE_*` — scope.
- `DOM_*`, `SYS_*` — domain/system context.
- `ARCH_*` — architecture patterns.
- `INDEX_*` — file/symbol lookup.

## State Memory Format

Every `WF_*` memory follows this structure:

```markdown
# WF_[NAME] - [Description]

> **On step WF_[NAME]**

OUTPUT THE ABOVE LINE IMMEDIATELY...

---

## Execute These Steps

[Numbered steps with specific actions]

## MANDATORY NEXT STEP

| Condition   | MUST Read Next |
| ----------- | -------------- |
| [condition] | `WF_[STATE]`   |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**
```

## Modification Checklist

When modifying the workflow system:

- [ ] Read `CLAUDE_WORKFLOW` for full state diagram.
- [ ] Identify all affected states.
- [ ] Update `WF_*` memory content.
- [ ] Update transition tables in affected states.
- [ ] Update `CLAUDE_WORKFLOW` diagram if transitions change.
- [ ] Update `INDEX_WORKFLOWS_STATES` if states added/removed.
- [ ] Test affected paths manually.
- [ ] Update `SPEC_WORKFLOW_SKILLS` if skill integration changes.

## Dependencies

| Component        | Depends On                                                                       |
| ---------------- | -------------------------------------------------------------------------------- |
| `WF_CLASSIFY`    | `CLAUDE_OBLIGATIONS`, `INDEX_FEATURES`, WM, `MEMORY.md`, `FEATURE_*` |
| `WF_CLASSIFY`    | (also) `DOM_*`, `SYS_*`, `INDEX_*`                                                |
| `WF_ARCH_REVIEW` | `ARCH_INDEX`, `ARCH__`, `REF__`                                                   |
| `WF_VERIFY`      | `CLAUDE_OBLIGATIONS`, `ARCH_INDEX`                                                |
| Skills           | `REF_SKILL_PROTOCOLS`, WM                                                         |
