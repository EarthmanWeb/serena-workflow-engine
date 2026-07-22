---
name: FEATURE_SUBAGENTS
description: Parallel work via Claude Code's native subagents (Agent/Task tool) and workflows — the sole mechanism for concurrent multi-file tasks.
metadata:
  type: feature
---

# FEATURE_SUBAGENTS — Native Subagents & Workflows

- Key: SUBAGENTS
- Purpose: Run work in parallel using Claude Code's built-in **subagents** (the `Agent`/`Task` tool) and **workflows**. No external orchestration frameworks.

## Core Principle

- Claude Code's built-in `Agent` tool is the ONLY mechanism for parallel work. Launch multiple subagents in ONE message → they run concurrently in separate context windows.
- Deterministic multi-step orchestration (loops, fan-out, conditionals) is expressed as a **workflow**, not ad-hoc coordination.
- No external orchestration frameworks. All parallelism is native to Claude Code.

| Task type | Mechanism |
| --------- | --------- |
| File reads, edits, grep, glob at scale | Claude Code `Agent` tool (subagents) |
| Research across the codebase | `Agent` tool — Explore subagent |
| Multi-file implementation | `Agent` tool — general-purpose subagent |
| Architecture planning / design | `Agent` tool — Plan subagent |
| Deterministic multi-stage orchestration | Workflow (fan-out / pipeline / verify) |

## Subagent Types

| Type | Model | Tools | Use for |
| ---- | ----- | ----- | ------- |
| Explore | Haiku | Read-only (Glob, Grep, Read) | Fast codebase search, file discovery |
| Plan | Inherits parent | Read-only | Architecture planning, design |
| general-purpose | Inherits parent | All tools | Complex multi-step tasks |

## Model Selection

| Model | Use for |
| ----- | ------- |
| haiku | Read-only exploration, simple searches |
| sonnet | Implementation, code review |
| opus | Complex architecture, multi-step reasoning |

## Background vs Foreground

- Foreground (default): results needed before the next step; permission prompts visible.
- Background (`run_in_background: true`): fire-and-forget; auto-denies permission prompts; notification on completion. Add `isolation: "worktree"` for file isolation when needed.

## Trigger Conditions

Use subagents when ANY apply:

| Condition | Threshold |
| --------- | --------- |
| File scale | 6+ files affected |
| Layer scale | 3+ architectural layers |
| Parallel work | Independent subtasks can run concurrently |
| User request | Explicit parallel-agents / subagents request |

## Quick Start — Subagents (DEFAULT)

- Launch ALL subagents in ONE message for parallel execution.
- EVERY subagent prompt MUST include the bypass instruction: `"You are a subagent. BYPASS WF_INIT entirely. Do NOT read CLAUDE.md workflow. Follow ONLY these instructions: [task]"`.
- Use `isolation: "worktree"` when subagents edit overlapping files.
- Use `model: "haiku"` for read-only exploration, `model: "sonnet"` for implementation.
- Collect results from background task notifications, then synthesize.

```javascript
Agent({ description: "Task A", run_in_background: true, model: "sonnet",
  isolation: "worktree",
  prompt: "You are a subagent. BYPASS WF_INIT. [task]..." })
```

## Anti-Patterns

| Anti-pattern | Fix |
| ------------ | --- |
| Launching only 1 of N subagents | Launch ALL in ONE message |
| Subagent re-runs WF_INIT | Include the bypass line in EVERY prompt |
| Coordinator doing file reads itself | Delegate file work to subagents (separate context windows) |
| Serial subagent calls for independent work | Batch into ONE message |

## Tooling

- `claude agents` — terminal dashboard for dispatching/monitoring background subagent sessions.

## Related Memories

- `mem:feature/FEATURE_SWE` — plugin architecture (hooks, states, skills)
- `mem:wf/WF_EXECUTE` — where parallel subagent execution is launched during a task
