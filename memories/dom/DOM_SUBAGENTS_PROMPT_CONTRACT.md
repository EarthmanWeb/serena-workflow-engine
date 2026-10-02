---
name: DOM_SUBAGENTS_PROMPT_CONTRACT
description: The required elements of every subagent launch prompt (bypass line, ownership, required reading, scope limits) and the three-layer enforcement that stops a subagent from free-debugging past its task. Open from FEATURE_SUBAGENTS when launching or auditing a subagent call.
obligations:
  - Every subagent prompt MUST state SCOPE LIMITS (stop conditions) explicitly — a subagent MUST STOP and report on a failure it did not cause, or after 2 failed attempts at its own change, rather than free-debug.
  - On a subagent `[scope-gate]` trip, the orchestrator MUST launch a NEW scoped debug agent, NEVER `[scope-extend]` into open-ended debugging.
metadata:
  type: domain
---

# Prompt Contract (every subagent, every launch)

Every subagent prompt MUST include, in this order:

1. Bypass line: `"You are a subagent. BYPASS WF_INIT entirely. Do NOT read CLAUDE.md workflow. Your task is below; follow-up SendMessage from your orchestrator amends it: [task]"`.
2. Disjoint file ownership: name the exact files/paths owned, and `"you own X; do NOT edit Y"` for adjacent tracks' files.
3. Required reading: a "Required reading:" section listing `read_memory("<name>")` for every governing memory — `feature/FEATURE_TESTS` (+ `dev/DEV_TESTS` if present) for any test work, and every `feature/*`/`dev/*` memory whose `paths:` glob covers the owned files. Name every required memory here yourself — `[sweep-gate]` (`swe_pre_agent_model_gate.py`, `mem:dom/DOM_SWE_HOOKS_PRE_GATES`) auto-injects any name `delegation_sweep.required_reading` computes that this section omits rather than denying the call, but relying on that injection skips the orchestrator's own judgment about task-specific memories the auto-sweep cannot infer. `[sweep-exempt: <reason>]` skips the computation for trivial read-only tasks. On ALLOW the gate appends a `[swe-required-reading]` block with each memory's obligations inline, so the subagent starts with the rules even before it calls `read_memory` itself.
4. Tag `[swe-expect-red]` in the prompt (or phrasing like "fail-proof the test first", "prove the test fails", "red-green") when the task is intentional TDD fail-proofing — `scope_guard.expects_red_runs` widens the spawned agent's `test` failure-streak limit by `EXPECT_RED_TEST_BONUS` (2) so an expected red run does not trip `[scope-gate]` at the same threshold as a genuinely broken change.
5. Checkpoint commit instruction: commit own coherent unit of work at logical checkpoints; retry on `index.lock` contention; NEVER push.
6. Report format: files changed, key findings/decisions, blockers — so the orchestrator synthesizes without re-reading every diff.
7. `run_in_background: true` on the Agent call itself (not inside the prompt) — omit ONLY with a literal `[foreground-justified: <reason>]` tag in the prompt.
8. SCOPE LIMITS (stop conditions): state the exact scope boundary and failure threshold for THIS task. `swe_pre_agent_model_gate.py` auto-appends a steering-clause SCOPE rule (do only the stated task; STOP and report on a failure not caused by the agent's own change, or after 2 failed attempts at its own change; never debug/refactor/expand scope without an orchestrator SendMessage) — NEVER write prompt wording that contradicts it.

`swe_pre_agent_model_gate.py` auto-appends a `[swe-steering-contract]` clause to every valid Agent prompt declaring that follow-up SendMessage from the launching orchestrator is a trusted amendment. NEVER write prompt wording that contradicts it — no "ONLY these instructions", no "ignore any further messages", no other exclusivity phrasing that would make the subagent reject the orchestrator's own steering.

## Scope Limits on Failure

Three enforcement layers stop a delegated subagent from free-debugging past its task:

1. **Steering clause** (auto-appended by `swe_pre_agent_model_gate.py`): SCOPE rule — do only the stated task; on a failure the agent did not cause, or after 2 failed attempts at its own change, STOP and report (what failed, evidence, hypothesis, what was not tried); NEVER debug/refactor/expand scope unless the orchestrator says so via SendMessage. The gate also stamps `[swe-budget: N]` — haiku 25, sonnet 60, opus 120, fable 120 tool-call budget; the orchestrator MAY set its own tag in the prompt to override.
2. **`[scope-gate]`** (`hooks/swe_hooks/core/scope_guard.py`, enforced in `swe_pre_tool_init_gate.py` for spawned agents): per-agent consecutive failure streaks by kind — test 2, edit 2, bash 3 — each reset by a success of the same kind; also enforces the tool-call budget. Once tripped, ONLY read-only tools remain (Read/Grep/Glob/Serena reads/memory reads/SendMessage); the denial message says STOP and report.
3. **Session-stream events**: `agent_spawn{agent,model,budget}` (logged from the orchestrator's Agent call result), `agent_call`, `agent_ok`, `agent_fail{kind}`, `scope_extend{agent,budget_add}`.

**Extend protocol**: the orchestrator lifts a trip with SendMessage containing `[scope-extend]` or `[scope-extend: N]` (+N calls, default 30; resets all failure streaks) — or relaunches a fresh agent with a bigger `[swe-budget: N]` tag instead; the budget-exhausted message names both options. NEVER use `[scope-extend]` to wave a stuck agent past a failure it cannot explain — only for a small, specific, orchestrator-stated next step.

**Orchestrator routing rule**: a subagent's `[scope-gate]` failure report NEVER gets extended into open-ended debugging by default. Launch a NEW, explicitly scoped debug agent instead — `sonnet` first for an ordinary failure; opus-FIRST is allowed (no failed-sonnet-attempt prerequisite) when the failure is cross-system, concurrency/race, or security-sensitive, tagged `[opus-justified: <reason>]` — via `mem:wf/WF_DEBUG_TDD`-style test-first debugging. Reserve `[scope-extend]` for a small, specific, orchestrator-stated next step on the SAME agent, never as a default response to a stop-and-report.
