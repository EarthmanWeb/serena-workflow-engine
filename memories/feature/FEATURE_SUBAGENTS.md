---
name: FEATURE_SUBAGENTS
description: Canonical authority for orchestrator-mode swarm delegation — when the main agent MUST fan out to parallel subagents instead of doing task work itself, model-tier routing, and the stage loop. Parallel work via Claude Code's native subagents (Agent/Task tool) and workflows.
paths:
  - hooks/pre/swe_pre_agent_model_gate.py
  - hooks/post/swe_post_orchestrator_drift.py
obligations:
  - Fan out to parallel background subagents (ONE message, disjoint file ownership) whenever ≥2 independent subtasks exist, 6+ files are affected, or 3+ layers are touched — the orchestrator itself only classifies, routes, and synthesizes.
  - Every Agent call MUST pass `model` explicitly per `mem:dom/DOM_SUBAGENTS_MODEL_ROUTING` (haiku for routine/mechanical, sonnet for implementation, opus REQUIRED for novel design/hard cross-file debugging/security/concurrency-FSM logic/broad refactors/explicit operator request — tag `[opus-justified: <reason>]`, NEVER downgraded to clear the gate), MUST include the "BYPASS WF_INIT" prompt line, and MUST pass `run_in_background: true` unless the prompt carries a literal `[foreground-justified: <reason>]` tag.
  - Any work that waits/polls (test runs, builds, CI, deploys, remote queues, a background process) MUST be delegated to ONE background subagent that runs the work AND polls it itself, then reports on completion — the orchestrator MUST NOT start it via `Bash run_in_background` and poll it with a blocking loop.
  - Every subagent prompt MUST state SCOPE LIMITS (stop conditions) explicitly per `mem:dom/DOM_SUBAGENTS_PROMPT_CONTRACT` — a subagent MUST STOP and report on a failure it did not cause, or after 2 failed attempts at its own change, rather than free-debug; on a `[scope-gate]` trip the orchestrator MUST launch a NEW scoped debug agent, NEVER `[scope-extend]` into open-ended debugging.
  - When 2+ agents share a repo, the orchestrator MUST write a WM Blueprint (tracks, OWNS, do-not-touch, sequencing) BEFORE spawning per `mem:dom/DOM_SUBAGENTS_PROMPT_CONTRACT` Multi-Agent Comms — every agent reads it at start and whenever unsure.
  - `swe_pre_agent_model_gate.py`'s `[sweep-gate]` auto-injects required reading when the orchestrator's prompt omits it, then ALLOWS the call — this does NOT relieve the orchestrator: name every required memory in the prompt yourself up front and record the task's sweep in WM BEFORE delegating. See `mem:dom/DOM_SWE_HOOKS_PRE_GATES_AGENT`.
metadata:
  type: feature
---

# FEATURE_SUBAGENTS — Orchestrator-Mode Swarm Delegation (Canonical)

- Key: SUBAGENTS
- Purpose: Run work in parallel using Claude Code's built-in **subagents** (the `Agent`/`Task` tool) and **workflows**. No external orchestration frameworks.

## When to Read a Child

| When                                                                          | Read                                       |
| ----------------------------------------------------------------------------- | ------------------------------------------ |
| Subagent types, foreground/background, launch example, anti-patterns          | `mem:dom/DOM_SUBAGENTS_REFERENCE`          |
| Launching a Serena edit/write call                                            | `mem:ref/REF_WF_EXECUTE_SERENA_EDIT_TOOLS` |
| Picking a model tier, Opus-required triggers, drift-counter thresholds        | `mem:dom/DOM_SUBAGENTS_MODEL_ROUTING`      |
| Writing/auditing a subagent launch prompt, scope-limit enforcement on failure | `mem:dom/DOM_SUBAGENTS_PROMPT_CONTRACT`    |

## Orchestrator Mode Is the DEFAULT

Single-agent delegation to a swarm of subagents is the standard operating mode, not an escalation. The main agent is an ORCHESTRATOR: classify, split into independent tracks with disjoint file ownership, launch ALL tracks as parallel background subagents in ONE message, collect results, verify, chain the next stage immediately. The orchestrator does NOT do the task work itself.

Orchestrator mode APPLIES when ANY hold: 2+ independent subtasks can run concurrently, operator asks to parallelize/use subagents/swarm, 6+ files affected, or 3+ architectural layers touched.

The orchestrator may do ITSELF, and ONLY this:

- Classification (task type, feature routing, thresholds above).
- Memory reads needed to route work to the right tracks.
- WM updates (`swe_wm_update*`).
- Single tiny coordination edits — ≤5 lines, e.g. a shared index/manifest line, a WM note.
- Synthesis and verification of agent results (reading diffs, running the checklist against reported changes).
- Commits/push, per the project's commit pipeline.

Everything else — file edits, test runs, greps/searches beyond routing, implementation, fixes — goes to a subagent. An orchestrator that reads target source files, runs `find_symbol`/`search_for_pattern` to scope an edit, or writes the fix itself has reverted to single-agent mode: STOP, split the remaining work, launch a subagent instead.

## Stage Loop

1. Fan out — launch ALL tracks for this stage as parallel background subagents in ONE message.
2. Collect — wait for background-task notifications; do not poll.
3. Fix via NEW agents — when an agent reports a defect or gap, launch a NEW subagent to fix it. NEVER make the fix yourself.
4. Chain immediately — the moment a stage's results are verified, launch the next stage's subagents in the same turn. Do not pause for a summary-only checkpoint when more parallel work is ready.

Exception — single-agent (or the orchestrator itself) may continue a TIGHT coupled-fix loop only when: the remaining work is on ONE shared file, changes are small (a few lines), and splitting would cost more in coordination than it saves. State the reason in the response when invoking this exception.

## Polling Work Goes to a Subagent

Any task requiring waiting or polling for completion — long test runs, builds, CI runs, deploys, remote queues, a background process whose result must be checked — MUST be delegated to a background subagent (`Agent` with `run_in_background: true`) that both runs the work AND performs the polling itself, then reports the result. The orchestrator MUST NOT start the work with `Bash run_in_background` and then poll it with a blocking poller in the main turn (`until ...; do sleep N; done`, `sleep` + re-check loops, repeated `gh run view`/status/`tail` checks, or a `Monitor` loop held open on the orchestrator). Route: haiku for status-only polling, sonnet when failures found during polling must be diagnosed. A blocking poller idles the orchestrator's premium-model turn exactly like a foreground agent; delegating absorbs the wait on a cheaper tier and the orchestrator is notified only on completion.

## Related Memories

- `mem:dom/DOM_SUBAGENTS_MODEL_ROUTING` — model-tier table, Opus-required triggers, drift enforcement, cheap-output verification rule
- `mem:dom/DOM_SUBAGENTS_PROMPT_CONTRACT` — required prompt elements, scope-limit enforcement layers
- `mem:dom/DOM_SUBAGENTS_REFERENCE` — subagent types, launch example, anti-pattern table
- `mem:feature/FEATURE_SWE` — plugin architecture (hooks, states, skills)
- `mem:wf/WF_EXECUTE` — where parallel subagent execution is launched during a task
- `mem:wf/WF_ARCH_REVIEW` — plans parallel tracks before execution
- `mem:wf/WF_CLASSIFY` — thresholds for routing to parallel-subagent mode
- `mem:claude/CLAUDE_OBLIGATIONS` — orchestrator-default one-liner
