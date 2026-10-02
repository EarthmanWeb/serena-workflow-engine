---
name: DOM_SUBAGENTS_MODEL_ROUTING
description: Model-tier routing table for Agent calls, the Opus-required trigger list, and orchestrator-drift enforcement thresholds. Open from FEATURE_SUBAGENTS when picking a model tier or auditing drift behavior.
obligations:
  - Every `Agent` call MUST pass `model` explicitly per the routing table — haiku routine/mechanical, sonnet implementation, opus REQUIRED for novel design/hard cross-file debugging/security/concurrency-FSM logic/broad refactors/explicit operator request (tag `[opus-justified: <reason>]`, NEVER downgraded to clear the gate).
  - Only BACKGROUND delegations (`run_in_background: true`) or a `Workflow` call reset the orchestrator-drift counter — a foreground Agent/Task call counts as task_work, same as Edit/Write/Bash.
  - NEVER write `single-agent:` pre-emptively — only a line added AFTER the drift hard block (weighted sum ≥12; reads 0.5, edits 1.0) disarms it, and only until the next background delegation.
metadata:
  type: domain
---

# Model-Tier Routing & Delegation Economics

Parallel execution + routing to the cheapest sufficient model is THE token-reduction mechanism for this harness — enforced by hooks, not left to judgment. Every `Agent` call MUST pass `model` EXPLICITLY — NEVER omit it or rely on inherited default. Every `Agent` call MUST also pass `run_in_background: true` explicitly — foreground requires a literal `[foreground-justified: <reason>]` tag in the prompt; no subagent_type exemption.

| Model  | Use for                                                                                                                                                                                                                                 |
| ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| haiku  | Routine/mechanical: test suites, lint, grep/inventory sweeps, read-only audits, link checks, status collection                                                                                                                          |
| sonnet | Implementation, doc rewrites, bug fixes, verification of cheap-agent output, ordinary test-failure diagnosis                                                                                                                            |
| opus   | Novel architecture/design; hard debugging (root cause unclear, cross-file/cross-system); security-sensitive changes; concurrency/state-machine/FSM logic; broad refactors spanning many modules; explicit operator request ("use opus") |
| fable  | NEVER without a literal `[fable-justified: <reason>]` tag in the prompt                                                                                                                                                                 |

## Opus REQUIRED

When ANY hold — novel design, hard/cross-file/cross-system debugging, security-sensitive change, concurrency/state-machine/FSM logic, broad multi-module refactor, or explicit operator request — use `model: "opus"` tagged `[opus-justified: <reason>]`. NEVER downgrade to sonnet/haiku to clear the routine-opus gate check — the gate itself allows opus here. Sonnet-first applies ONLY to ordinary test-failure debugging where the cause is not yet known to be cross-system/concurrency/security.

- The orchestrator ALREADY runs the premium model. Delegation moves work OFF it, never spends a second premium call on work a cheaper tier can do.
- `opus` tag alias: `[premium-justified: <reason>]` ≡ `[opus-justified: <reason>]` — reason required, no bare tag.
- `fable` tag `[fable-justified: <reason>]` (or `[premium-justified: <reason>]`) REQUIRED on every `fable`-model call, no exception for "routine" vs "novel".
- ALL independent tracks launch in ONE message, never sequential single-track calls for independent work.
- Verification economy: ONE full-suite run per verified stage, by ONE haiku agent, at stage END. Implementation agents run ONLY `py_compile` + tests scoped to owned files. NEVER re-run an already-green suite "to double-check".
- `swe_pre_agent_model_gate.py` enforces this: Agent calls without `model` + bypass line denied; routine-task `opus` requests denied UNLESS the prompt also carries a design keyword OR a complexity keyword (debug, root cause, security, auth, concurrency, race, deadlock, state machine, cross-file, cross-system, regression, flaky) — either overrides the routine-keyword deny; `fable` without justification tag denied; Agent/Task calls without `run_in_background: true` and without a `[foreground-justified: <reason>]` tag denied.

## Drift Enforcement

The main agent NEVER burns premium-model tokens on routine tool loops. `swe_post_orchestrator_drift.py` sums WEIGHTED main-agent task-work calls since the last delegation. Only BACKGROUND delegations reset the counter — `Agent`/`Task` with `run_in_background: true`, or any `Workflow` call. A FOREGROUND `Agent`/`Task` call does NOT reset the counter; it counts as `task_work` at full weight.

- Weight 1.0: edits/writes, Serena edit tools, mutating Bash, foreground Agent/Task.
- Weight 0.5: reads, searches (Read/Grep/Glob), inspection/verification Bash, every non-delegation MCP tool (Serena read/symbol, jira, browser-devtools, wp-cli).
- Weight 0 (never trips the brake): Serena memory tools, swe-wm MCP tools, ToolSearch, AskUserQuestion, TodoWrite, Skill, SendMessage.
- At weighted sum ≥ 6 (`DRIFT_THRESHOLD`) — advisory nudge to split remaining work into parallel background subagents (12 reads reach it).
- At weighted sum ≥ 12 (`DRIFT_HARD_THRESHOLD`) — `swe_pre_edit_validate.py` DENIES further main-agent edits until either a BACKGROUND subagent is launched (or a Workflow call is made — this resets the counter) or a NEW `single-agent: <reason>` line is recorded in WM `## Workflow Context` — the tight single-file coupled-fix exception ONLY (`mem:feature/FEATURE_SUBAGENTS` Stage Loop), not a routine bypass.
- NEVER write `single-agent:` pre-emptively — a note present before the hard block fires is snapshotted into the `drift_hard_block` event and NEVER disarms. Only a line added AFTER the block disarms it, and only until the next background delegation; the next hard block requires a fresh line.

## Cheap-Output Verification Rule

- Treat haiku findings as LEADS, never verified fact. A sonnet agent (or the fix agent acting on the finding) re-verifies against the actual code before acting on a haiku report.
- A negative haiku result ("0 found", "nothing matches") REQUIRES a positive control — one probe proving the search method can detect the target when present — before it is trusted. An unvalidated negative is "probe unverified", not "confirmed absent".
