---
name: FEATURE_SUBAGENTS
description: Canonical authority for orchestrator-mode swarm delegation — when the main agent MUST fan out to parallel subagents instead of doing task work itself, model-tier routing, and the stage loop. Parallel work via Claude Code's native subagents (Agent/Task tool) and workflows.
obligations:
  - Fan out to parallel background subagents (ONE message, disjoint file ownership) whenever ≥2 independent subtasks exist, 6+ files are affected, or 3+ layers are touched — the orchestrator itself only classifies, routes, and synthesizes.
  - Every Agent call MUST pass `model` explicitly per the routing table (haiku for routine/mechanical, sonnet for implementation, opus only for novel design or after a failed sonnet attempt) and MUST include the "BYPASS WF_INIT" prompt line.
metadata:
  type: feature
---

# FEATURE_SUBAGENTS — Orchestrator-Mode Swarm Delegation (Canonical)

- Key: SUBAGENTS
- Purpose: Run work in parallel using Claude Code's built-in **subagents** (the `Agent`/`Task` tool) and **workflows**. No external orchestration frameworks.

## Orchestrator Mode Is the DEFAULT

Single-agent delegation to a swarm of subagents is the standard operating mode, not an escalation. The main agent is an ORCHESTRATOR: classify, split into independent tracks with disjoint file ownership, launch ALL tracks as parallel background subagents in ONE message, collect results, verify, chain the next stage immediately. The orchestrator does NOT do the task work itself.

Orchestrator mode APPLIES when ANY hold:

| Condition                | Threshold                                            |
| ------------------------ | ---------------------------------------------------- |
| Independent subtasks     | 2 or more can run concurrently                       |
| Explicit fan-out request | Operator asks to parallelize / use subagents / swarm |
| File scale               | 6+ files affected                                    |
| Layer scale              | 3+ architectural layers                              |

The orchestrator may do ITSELF, and ONLY this:

- Classification (task type, feature routing, thresholds above).
- Memory reads needed to route work to the right tracks.
- WM updates (`swe_wm_update*`).
- Single tiny coordination edits — ≤5 lines, e.g. a shared index/manifest line, a WM note.
- Synthesis and verification of agent results (reading diffs, running the checklist against reported changes).
- Commits/push, per the project's commit pipeline.

Everything else — file edits, test runs, greps/searches beyond routing, implementation, fixes — goes to a subagent. An orchestrator that reads target source files, runs `find_symbol`/`search_for_pattern` to scope an edit, or writes the fix itself has silently reverted to single-agent mode: STOP, split the remaining work, and launch a subagent for it instead.

## Stage Loop

1. Fan out — launch ALL tracks for this stage as parallel background subagents in ONE message.
2. Collect — wait for background-task notifications; do not poll.
3. Fix via NEW agents — when an agent reports a defect or gap, launch a NEW subagent to fix it. NEVER make the fix yourself.
4. Chain immediately — the moment a stage's results are verified, launch the next stage's subagents in the same turn. Do not pause for a summary-only checkpoint when more parallel work is ready.

Exception — single-agent (or the orchestrator itself) may continue a TIGHT coupled-fix loop only when: the remaining work is on ONE shared file, changes are small (a few lines), and splitting would cost more in coordination than it saves. State the reason in the response when invoking this exception.

## Model-Tier Routing (MANDATORY on every Agent call)

Every `Agent` call MUST pass `model` EXPLICITLY. NEVER omit `model` / rely on inherited default.

| Model  | Use for                                                                                                                                        |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| haiku  | Routine/mechanical: run test suites, lint, grep/inventory sweeps, read-only audits against a precise checklist, link checks, status collection |
| sonnet | Implementation, doc rewrites, bug fixes, verification of cheap-agent output, test-failure diagnosis                                            |
| opus   | ONLY: novel architecture/design, cross-system debugging after a sonnet attempt failed, or explicit operator request                            |
| fable  | NEVER for subagents without a literal `[fable-justified: <reason>]` tag in the prompt                                                          |

- The orchestrator ALREADY runs the premium model. Delegation exists to move work OFF it, never to spend a second premium call on work a cheaper tier can do.
- `opus` tag alias: `[premium-justified: <reason>]` is accepted interchangeably with `[opus-justified: <reason>]` — same enforcement, same requirement (reason required, no bare tag).
- `fable` tag: `[fable-justified: <reason>]` (or `[premium-justified: <reason>]`) is REQUIRED on every `fable`-model subagent call, no exceptions for "routine" vs "novel" — fable subagents are denied by default regardless of task shape.
- `swe_pre_agent_model_gate.py` enforces this: Agent calls without `model` + the bypass line are denied; a routine-task prompt requesting `opus` is denied; a `fable`-model subagent without the justification tag is denied.

## Delegation Economics

Parallel execution + routing work to the cheapest sufficient model is THE token-reduction mechanism for this harness, not a style preference. It is enforced by hooks, not left to judgment.

- Recon/inventory/grep sweeps, test runs, lint, link checks → `haiku`, launched in PARALLEL — ALL tracks in ONE message, never sequential single-track calls for independent work.
- Implementation, doc rewrites, verification of haiku output → `sonnet`.
- `opus` ONLY for novel design or after a `sonnet` attempt has already failed on the same problem.
- `fable` NEVER delegated without a `[fable-justified: <reason>]` (or `[premium-justified: <reason>]`) tag — see Model-Tier Routing above.
- Verification economy: ONE full-suite run per verified stage, by ONE agent (haiku), at the stage's END. Implementation agents run ONLY `py_compile` + the tests scoped to their owned files. NEVER re-run a suite that is already green this stage "to double-check" — a green result is the result.
- The main agent NEVER burns premium-model tokens on routine tool loops. `swe_post_orchestrator_drift.py` counts consecutive main-agent task-work calls since the last delegation:
  - At 6 consecutive calls (`DRIFT_THRESHOLD`) — advisory nudge to split remaining work into parallel subagents.
  - At 12 consecutive calls (`DRIFT_HARD_THRESHOLD`) — `swe_pre_edit_validate.py` DENIES further main-agent edits until either a subagent is launched (any delegation resets the counter) or `single-agent: <reason>` is recorded in WM `## Workflow Context` (the tight single-file coupled-fix exception from the Stage Loop section above — use it ONLY for that case, not as a routine bypass).

## Cheap-Output Verification Rule

- Treat haiku findings as LEADS, never as verified fact.
- A sonnet agent (or the fix agent that acts on the finding) re-verifies against the actual code before acting on a haiku report.
- A negative haiku result ("0 found", "nothing matches") REQUIRES a positive control — one probe proving the search method can detect the target when present — before it is trusted. An unvalidated negative is "probe unverified", not "confirmed absent".

## Prompt Contract (every subagent, every launch)

Every subagent prompt MUST include, in this order:

1. Bypass line: `"You are a subagent. BYPASS WF_INIT entirely. Do NOT read CLAUDE.md workflow. Follow ONLY these instructions: [task]"`.
2. Disjoint file ownership: name the exact files/paths this agent owns, and state `"you own X; do NOT edit Y"` for adjacent tracks' files.
3. Checkpoint commit instruction: commit its own coherent unit of work at logical checkpoints; retry on `index.lock` contention (another parallel agent committing); NEVER push.
4. Report format: what to return (files changed, key findings/decisions, blockers) so the orchestrator can synthesize without re-reading every diff.

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

| Anti-pattern                                             | Fix                                                                              |
| -------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Orchestrator doing file edits or running tests itself    | Delegate to a subagent — orchestrator does classification/routing/synthesis only |
| Serial agent calls for independent work                  | Batch ALL independent tracks into ONE message                                    |
| Launching only 1 of N subagents                          | Launch ALL in ONE message                                                        |
| Subagent re-runs WF_INIT                                 | Include the bypass line in EVERY prompt                                          |
| `opus` or inherited/omitted model for routine work       | Pass `model` explicitly; haiku/sonnet per the routing table                      |
| Trusting a haiku "0 findings" without a positive control | Re-verify with sonnet or a validated probe before acting on a negative           |
| Coordinator doing file reads itself                      | Delegate file work to subagents (separate context windows)                       |

## Enforcement

- `swe_pre_agent_model_gate.py` — Agent calls must set `model` + the bypass line; routine-task prompts denied on `opus`; `fable`-model subagents denied without `[fable-justified: <reason>]`/`[premium-justified: <reason>]`.
- WF_EXECUTE carries an orchestrator-drift nudge — flags the orchestrator when it starts doing file-edit/test-run work itself instead of delegating (6 consecutive calls, `DRIFT_THRESHOLD`).
- `swe_pre_edit_validate.py` — HARD BLOCK: denies main-agent edits at ≥12 consecutive undelegated task-work calls (`DRIFT_HARD_THRESHOLD`) until a delegation resets the counter or `single-agent: <reason>` is recorded in WM Context.

## Tooling

- `claude agents` — terminal dashboard for dispatching/monitoring background subagent sessions.

## Related Memories

- `mem:feature/FEATURE_SWE` — plugin architecture (hooks, states, skills)
- `mem:wf/WF_EXECUTE` — where parallel subagent execution is launched during a task
- `mem:wf/WF_ARCH_REVIEW` — plans parallel tracks before execution
- `mem:wf/WF_CLASSIFY` — thresholds for routing to parallel-subagent mode
- `mem:claude/CLAUDE_OBLIGATIONS` — orchestrator-default one-liner
