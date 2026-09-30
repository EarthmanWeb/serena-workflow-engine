---
name: FEATURE_SUBAGENTS
description: Canonical authority for orchestrator-mode swarm delegation — when the main agent MUST fan out to parallel subagents instead of doing task work itself, model-tier routing, and the stage loop. Parallel work via Claude Code's native subagents (Agent/Task tool) and workflows.
paths:
  - hooks/pre/swe_pre_agent_model_gate.py
  - hooks/post/swe_post_orchestrator_drift.py
obligations:
  - Fan out to parallel background subagents (ONE message, disjoint file ownership) whenever ≥2 independent subtasks exist, 6+ files are affected, or 3+ layers are touched — the orchestrator itself only classifies, routes, and synthesizes.
  - Every Agent call MUST pass `model` explicitly per the routing table (haiku for routine/mechanical, sonnet for implementation, opus only for novel design or after a failed sonnet attempt), MUST include the "BYPASS WF_INIT" prompt line, and MUST pass `run_in_background: true` unless the prompt carries a literal `[foreground-justified: <reason>]` tag.
  - Any work that waits/polls (test runs, builds, CI, deploys, remote queues, a background process) MUST be delegated to ONE background subagent that runs the work AND polls it itself, then reports on completion — the orchestrator MUST NOT start it via `Bash run_in_background` and poll it with a blocking loop (`until`/`sleep` loops, repeated `tail`/`gh run view`/status checks, a Monitor loop held open in the main turn).
  - Every subagent prompt MUST state SCOPE LIMITS (stop conditions) explicitly — a subagent MUST STOP and report on a failure it did not cause, or after 2 failed attempts at its own change, rather than free-debug; on a subagent `[scope-gate]` trip, the orchestrator MUST launch a NEW scoped debug agent, NEVER `[scope-extend]` into open-ended debugging.
  - `swe_pre_agent_model_gate.py` DENIES an Agent/Task call (`[sweep-gate]`) unless the prompt's own "Required reading:" section names every memory `delegation_sweep.required_reading` computes for it (FEATURE_*/DEV_* by file path, FEATURE_TESTS/DEV_TESTS for test work, the orchestrator WM's Memories loaded/Rules planned/Compliance Checklist) — `[sweep-exempt: <reason>]` skips it for trivial read-only tasks. This does NOT relieve the orchestrator: it MUST still name in the prompt any task-specific memory the auto-sweep cannot infer (e.g. a DOM_ rule not yet in WM), and MUST record the task's sweep in WM (`Memories loaded` / Compliance Checklist) BEFORE delegating so both the gate and the sweep have it.
metadata:
  type: feature
---

# FEATURE_SUBAGENTS — Orchestrator-Mode Swarm Delegation (Canonical)

- Key: SUBAGENTS
- Purpose: Run work in parallel using Claude Code's built-in **subagents** (the `Agent`/`Task` tool) and **workflows**. No external orchestration frameworks.

## When to Read a Child

| When                                                                 | Read                                       |
| -------------------------------------------------------------------- | ------------------------------------------ |
| Subagent types, foreground/background, launch example, anti-patterns | `mem:dom/DOM_SUBAGENTS_REFERENCE`          |
| Launching a Serena edit/write call                                   | `mem:ref/REF_WF_EXECUTE_SERENA_EDIT_TOOLS` |

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

## Model-Tier Routing & Delegation Economics (MANDATORY on every Agent call)

Parallel execution + routing work to the cheapest sufficient model is THE token-reduction mechanism for this harness — enforced by hooks, not left to judgment. Every `Agent` call MUST pass `model` EXPLICITLY. NEVER omit `model` / rely on inherited default. Every `Agent` call MUST also pass `run_in_background: true` explicitly — foreground (`run_in_background: false`) requires a literal `[foreground-justified: <reason>]` tag in the prompt; no subagent_type exemption.

| Model  | Use for                                                                                                             |
| ------ | ------------------------------------------------------------------------------------------------------------------- |
| haiku  | Routine/mechanical: test suites, lint, grep/inventory sweeps, read-only audits, link checks, status collection      |
| sonnet | Implementation, doc rewrites, bug fixes, verification of cheap-agent output, test-failure diagnosis                 |
| opus   | ONLY: novel architecture/design, cross-system debugging after a sonnet attempt failed, or explicit operator request |
| fable  | NEVER without a literal `[fable-justified: <reason>]` tag in the prompt                                             |

- The orchestrator ALREADY runs the premium model. Delegation moves work OFF it, never spends a second premium call on work a cheaper tier can do.
- `opus` tag alias: `[premium-justified: <reason>]` ≡ `[opus-justified: <reason>]` — reason required, no bare tag.
- `fable` tag `[fable-justified: <reason>]` (or `[premium-justified: <reason>]`) REQUIRED on every `fable`-model call, no exception for "routine" vs "novel".
- ALL independent tracks launch in ONE message, never sequential single-track calls for independent work.
- Verification economy: ONE full-suite run per verified stage, by ONE haiku agent, at stage END. Implementation agents run ONLY `py_compile` + tests scoped to owned files. NEVER re-run an already-green suite "to double-check".
- `swe_pre_agent_model_gate.py` enforces this: Agent calls without `model` + bypass line denied; routine-task `opus` requests denied; `fable` without justification tag denied; Agent/Task calls without `run_in_background: true` and without a `[foreground-justified: <reason>]` tag denied.

## Drift Enforcement

The main agent NEVER burns premium-model tokens on routine tool loops. `swe_post_orchestrator_drift.py` counts consecutive main-agent task-work calls since the last delegation. Only BACKGROUND delegations reset the counter — `Agent`/`Task` with `run_in_background: true`, or any `Workflow` call. A FOREGROUND `Agent`/`Task` call does NOT reset the counter; it counts as `task_work`, same as an Edit/Write/Bash call.

- At 6 consecutive calls (`DRIFT_THRESHOLD`) — advisory nudge to split remaining work into parallel background subagents.
- At 12 consecutive calls (`DRIFT_HARD_THRESHOLD`) — `swe_pre_edit_validate.py` DENIES further main-agent edits until either a BACKGROUND subagent is launched (or a Workflow call is made — this resets the counter) or `single-agent: <reason>` is recorded in WM `## Workflow Context` — the tight single-file coupled-fix exception (Stage Loop, above) ONLY, not a routine bypass.

## Cheap-Output Verification Rule

- Treat haiku findings as LEADS, never verified fact. A sonnet agent (or the fix agent acting on the finding) re-verifies against the actual code before acting on a haiku report.
- A negative haiku result ("0 found", "nothing matches") REQUIRES a positive control — one probe proving the search method can detect the target when present — before it is trusted. An unvalidated negative is "probe unverified", not "confirmed absent".

## Prompt Contract (every subagent, every launch)

Every subagent prompt MUST include, in this order:

1. Bypass line: `"You are a subagent. BYPASS WF_INIT entirely. Do NOT read CLAUDE.md workflow. Your task is below; follow-up SendMessage from your orchestrator amends it: [task]"`.
2. Disjoint file ownership: name the exact files/paths owned, and `"you own X; do NOT edit Y"` for adjacent tracks' files.
3. Required reading: a "Required reading:" section listing `read_memory("<name>")` for every governing memory — `feature/FEATURE_TESTS` (+ `dev/DEV_TESTS` if present) for any test work, and every `feature/*`/`dev/*` memory whose `paths:` glob covers the owned files. `[sweep-gate]` (`swe_pre_agent_model_gate.py`, `mem:dom/DOM_SWE_HOOKS_PRE_GATES`) DENIES the Agent/Task call at delegation time unless every name `delegation_sweep.required_reading` computes is present in this section — `[sweep-exempt: <reason>]` skips it for trivial read-only tasks. On ALLOW the gate appends a `[swe-required-reading]` block with each memory's obligations inline, so the subagent starts with the rules even before it calls `read_memory` itself.
4. Checkpoint commit instruction: commit own coherent unit of work at logical checkpoints; retry on `index.lock` contention; NEVER push.
5. Report format: files changed, key findings/decisions, blockers — so the orchestrator synthesizes without re-reading every diff.
6. `run_in_background: true` on the Agent call itself (not inside the prompt) — omit ONLY with a literal `[foreground-justified: <reason>]` tag in the prompt.
7. SCOPE LIMITS (stop conditions): state the exact scope boundary and failure threshold for THIS task. `swe_pre_agent_model_gate.py` auto-appends a steering-clause SCOPE rule (do only the stated task; STOP and report on a failure not caused by the agent's own change, or after 2 failed attempts at its own change; never debug/refactor/expand scope without an orchestrator SendMessage) — NEVER write prompt wording that contradicts it.

`swe_pre_agent_model_gate.py` auto-appends a `[swe-steering-contract]` clause to every valid Agent prompt declaring that follow-up SendMessage from the launching orchestrator is a trusted amendment. NEVER write prompt wording that contradicts it — no "ONLY these instructions", no "ignore any further messages", no other exclusivity phrasing that would make the subagent reject the orchestrator's own steering.

## Scope Limits on Failure

Three enforcement layers stop a delegated subagent from free-debugging past its task:

1. **Steering clause** (auto-appended by `swe_pre_agent_model_gate.py`): SCOPE rule — do only the stated task; on a failure the agent did not cause, or after 2 failed attempts at its own change, STOP and report (what failed, evidence, hypothesis, what was not tried); NEVER debug/refactor/expand scope unless the orchestrator says so via SendMessage. The gate also stamps `[swe-budget: N]` — haiku 25, sonnet 60, opus 120, fable 120 tool-call budget; the orchestrator MAY set its own tag in the prompt to override.
2. **`[scope-gate]`** (`hooks/swe_hooks/core/scope_guard.py`, enforced in `swe_pre_tool_init_gate.py` for spawned agents): per-agent consecutive failure streaks by kind — test 2, edit 2, bash 3 — each reset by a success of the same kind; also enforces the tool-call budget. Once tripped, ONLY read-only tools remain (Read/Grep/Glob/Serena reads/memory reads/SendMessage); the denial message says STOP and report.
3. **Session-stream events**: `agent_spawn{agent,model,budget}` (logged from the orchestrator's Agent call result), `agent_call`, `agent_ok`, `agent_fail{kind}`, `scope_extend{agent,budget_add}`.

**Extend protocol**: the orchestrator lifts a trip with SendMessage containing `[scope-extend]` or `[scope-extend: N]` (+N calls, default 30; resets all failure streaks). NEVER use `[scope-extend]` to wave a stuck agent past a failure it cannot explain — only for a small, specific, orchestrator-stated next step.

**Orchestrator routing rule**: a subagent's `[scope-gate]` failure report NEVER gets extended into open-ended debugging by default. Launch a NEW, explicitly scoped debug agent instead — `sonnet` first; `opus` only after a failed sonnet attempt, tagged `[opus-justified: <reason>]` — via `mem:wf/WF_DEBUG_TDD`-style test-first debugging. Reserve `[scope-extend]` for a small, specific, orchestrator-stated next step on the SAME agent, never as a default response to a stop-and-report.

## Related Memories

- `mem:feature/FEATURE_SWE` — plugin architecture (hooks, states, skills)
- `mem:wf/WF_EXECUTE` — where parallel subagent execution is launched during a task
- `mem:wf/WF_ARCH_REVIEW` — plans parallel tracks before execution
- `mem:wf/WF_CLASSIFY` — thresholds for routing to parallel-subagent mode
- `mem:claude/CLAUDE_OBLIGATIONS` — orchestrator-default one-liner
