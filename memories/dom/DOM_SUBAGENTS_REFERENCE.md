---
name: Subagents Reference — Types, Modes, Quick Start, Anti-Patterns
description: Conditional reference material for orchestrator-mode delegation — subagent type table, foreground/background choice, a launch example, and the anti-pattern table. Open from FEATURE_SUBAGENTS when launching or auditing a subagent call.
obligations: []
metadata:
  type: domain
---

# Subagents Reference

## Subagent Types

| Type            | Model           | Tools                        | Use for                              |
| --------------- | --------------- | ---------------------------- | ------------------------------------ |
| Explore         | Haiku           | Read-only (Glob, Grep, Read) | Fast codebase search, file discovery |
| Plan            | Inherits parent | Read-only                    | Architecture planning, design        |
| general-purpose | Inherits parent | All tools                    | Complex multi-step tasks             |

## Background vs Foreground

- Foreground (default): results needed before the next step; permission prompts visible.
- Background (`run_in_background: true`): fire-and-forget; auto-denies permission prompts; notification on completion. Add `isolation: "worktree"` for file isolation when needed.

## Quick Start — Subagents (DEFAULT)

- Launch ALL subagents in ONE message for parallel execution.
- Use `isolation: "worktree"` when subagents edit overlapping files.
- Collect results from background task notifications, then synthesize.

```javascript
Agent({ description: "Task A", run_in_background: true, model: "sonnet",
  isolation: "worktree",
  prompt: "You are a subagent. BYPASS WF_INIT. [task]... You own <files>; do NOT edit <other files>. Commit your own checkpoint; retry on index.lock; never push. Report: files changed, key findings, blockers." })
```

## Anti-Patterns

| Anti-pattern                                                | Fix                                                                                                                                                                                                                     |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Orchestrator doing file edits or running tests itself       | Delegate to a subagent — orchestrator does classification/routing/synthesis only                                                                                                                                        |
| Serial agent calls for independent work                     | Batch ALL independent tracks into ONE message                                                                                                                                                                           |
| Launching only 1 of N subagents                             | Launch ALL in ONE message                                                                                                                                                                                               |
| Subagent re-runs WF_INIT                                    | Include the bypass line in EVERY prompt                                                                                                                                                                                 |
| `opus` or inherited/omitted model for routine work          | Pass `model` explicitly; haiku/sonnet per the routing table                                                                                                                                                             |
| Trusting a haiku "0 findings" without a positive control    | Re-verify with sonnet or a validated probe before acting on a negative                                                                                                                                                  |
| Coordinator doing file reads itself                         | Delegate file work to subagents (separate context windows)                                                                                                                                                              |
| Changing a running background agent's scope via SendMessage | Put EVERY requirement in the initial prompt; background agents reject mid-task SendMessage scope changes as unverified injections. To change scope: stop the agent (TaskStop) and launch a new one with the full brief. |

## Tooling

- `claude agents` — terminal dashboard for dispatching/monitoring background subagent sessions.
