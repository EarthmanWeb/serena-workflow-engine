---
name: DOM_SWE_HOOKS_PRE_GATES_AGENT
description: PreToolUse agent model gate — five DENY checks, sweep-gate auto-inject, delegation_sweep sourcing, budget stamping, scope-gate SCOPE rule.
metadata:
  type: domain
obligations:
  - Agent model gate appends a `[swe-steering-contract]` clause via `updatedInput` on every ALLOW, declaring orchestrator SendMessage a trusted amendment and hook workflow banners orchestrator-only.
  - On ALLOW, stamp `[swe-budget: N]` by model (haiku 25, sonnet 60, opus 120, fable 120) and append `[swe-required-reading]` with each required memory's obligations inline.
  - `[scope-gate]` trips a spawned agent to read-only tools after consecutive failures (test 2, edit 2, bash 3) or budget exhaustion; only the orchestrator's `[scope-extend]` lifts it.
---

# DOM_SWE_HOOKS_PRE_GATES_AGENT — Agent Model Gate

Hub: `mem:dom/DOM_SWE_HOOKS_PRE_GATES`.

## `swe_pre_agent_model_gate.py` — PreToolUse (Agent/Task)

Enforces orchestrator + swarm delegation with complexity-based model tiers. FIVE independent DENY checks, plus a non-denying `[sweep-gate]` auto-inject:

1. Missing `model` param — required for every subagent_type except fixed-model built-ins (`claude-code-guide`, `statusline-setup`).
2. Prompt lacks the subagent bypass marker ("BYPASS WF_INIT" / "you are a subagent" / "swarm agent") — without it the spawned agent re-runs the init chain.
3. `model: "opus"` on a routine-keyword prompt (tests/lint/grep/inventory/read-only audit) with no design keyword AND no complexity keyword — override via literal `[opus-justified: <reason>]` tag in the prompt (`[premium-justified: <reason>]` accepted as an alias, same requirement). Design keywords: novel architecture/design, broad refactor. Complexity keywords: debug, root cause, security, auth, concurrency, race, deadlock, state machine, cross-file, cross-system, regression, flaky — either set overrides the routine-keyword deny; the denial message leads with the justify-tag option before any other remedy.
4. `model: "fable"` on ANY subagent call — fable is NEVER delegated by default, regardless of task shape — override via literal `[fable-justified: <reason>]` tag (`[premium-justified: <reason>]` alias also accepted).
5. `run_in_background` missing or `false` on ANY Agent/Task call with no literal `[foreground-justified: <reason>]` tag in the prompt — background is the DEFAULT and REQUIRED value; no subagent_type exemption.

`[sweep-gate]` is not a deny check — `_missing_sweep_names(prompt, required)` computes `required = delegation_sweep.required_reading(prompt, wm_text, project_root, cap=8)` and subtracts names already present in the orchestrator-written prompt (`[sweep-exempt: <reason>]` short-circuits to `[]`). Any names still missing are auto-injected into the prompt's "Required reading:" section via `with_missing_required_reading` (idempotent — a name already present anywhere in the prompt is never re-added) and the call is ALLOWED, with `permissionDecisionReason` naming which memories were auto-added (`📋 [sweep-gate] auto-added required reading: <names>`). `missing_sweep_reason` is the pure "what would be missing" message-builder (used by tests and by the auto-inject path).

Rationale: the orchestrator already runs the premium model; delegation moves work OFF it. Check 5's rationale: a foreground delegation blocks the orchestrator on one call with no parallelism and does not reset the drift counter (`mem:dom/DOM_SWE_HOOKS_POST`). `[sweep-gate]`'s rationale: the subagent's own `[doc-gate]`/per-agent bash-test gating are enforced only at the main agent (`mem:dom/DOM_SWE_HOOKS_PRE_GATES_DOCS`, `mem:dom/DOM_SWE_HOOKS_PRE_GATES`) — required reading for a subagent is enforced ONCE, at spawn time, by injecting it into the prompt rather than by forcing a relaunch round-trip.

## `delegation_sweep.required_reading` — sources, cap, idempotence

`hooks/swe_hooks/core/delegation_sweep.py` computes the sweep from THREE sources, capped at 8 memory names total:

1. `FEATURE_*`/`DEV_*` memories whose front-matter `paths:` glob matches a file path named in the prompt.
2. `feature/FEATURE_TESTS` + `dev/DEV_TESTS` (when present) for any prompt describing test work.
3. The orchestrator WM's `**Memories loaded**`, `**Rules planned**`, and `## Compliance Checklist` `(mem:…)` citations — excluding `wf/*`, `claude/*`, `WM_*`, and `spec/`/`report/`/`research/`/`project/` names.

On ALLOW, the gate appends a `[swe-required-reading]` block listing `read_memory("<name>")` per required memory PLUS that memory's front-matter `obligations:` inline — the subagent has the rules before it calls `read_memory` itself. Idempotent via a marker (never appended twice to the same prompt). Fails open: a `delegation_sweep` error never blocks the Agent call — treat `required_reading` as returning `[]` on internal failure, same as any other gate exception in this hook.

On ALLOW, the gate appends a `[swe-steering-contract]` clause to the Agent call's prompt via `updatedInput` (pure fn `with_steering_clause`) — declares that a follow-up SendMessage from the launching orchestrator is a trusted amendment (may narrow/expand/redirect scope, including read-only → implementation) and that hook workflow banners (ON STEP/CONTINUE/WF_*) surfaced during the run target the orchestrator, never the spawned agent. The same clause tells the subagent that `[doc-gate]` denials ARE addressed to IT (not the orchestrator): read each memory the denial names with `read_memory` before editing or running tests — the orchestrator's reads never count for the subagent. Applies to every passing call; never applied on a DENY.

### `doc_requirements.memory_roots` — plugin-source inclusion

`memory_roots(project_root)` also includes the plugin's shipped `memories/` root (not only `.serena/memory-paths.conf` entries) — `delegation_sweep.required_reading`'s FEATURE__/DEV__ path-match and FEATURE_TESTS/DEV_TESTS lookups resolve against BOTH the plugin source tree and this repo's local dev memories. A required memory that exists only in `memories/` (plugin source, ships to every installed repo) is named correctly, never silently dropped for living outside `.serena/memory/` (this repo's local-only dev memories).

Pure functions `missing_model_reason`/`missing_bypass_marker_reason`/`opus_on_routine_reason`/`fable_without_justification_reason`/`foreground_without_justification_reason`/`missing_sweep_reason`/`with_steering_clause` are unit-tested.

## Budget tag stamping + clause SCOPE rule

- On ALLOW, the gate stamps a `[swe-budget: N]` tag onto the spawned agent's tool-call budget by model: haiku 25, sonnet 60, opus 120, fable 120. The orchestrator MAY set its own tag in the prompt to override the default.
- The auto-appended steering clause carries a SCOPE rule: do only the stated task; on a failure the agent did not cause, or after 2 failed attempts at its own change, STOP and report (what failed, evidence, hypothesis, what was not tried); NEVER debug/refactor/expand scope unless the orchestrator says so via SendMessage.
- `[scope-gate]` (`hooks/swe_hooks/core/scope_guard.py`) enforces this budget and per-kind failure streaks (test 2, edit 2, bash 3, each reset by a same-kind success) at `swe_pre_tool_init_gate.py` for every spawned-agent tool call. A trip restricts the agent to read-only tools (Read/Grep/Glob/Serena reads/memory reads/SendMessage); the denial message says STOP and report.
- `scope_guard.expects_red_runs(prompt)` — true on a literal `[swe-expect-red]` tag or fail-proofing/red-green phrasing (`fail-proof`, `flip the assertion`, `expected-red`, `red-green`, `prove the test fails`, `intentionally failing`) in the SPAWNING prompt. When true, `agent_spawn` carries `expect_red: true` and `scope_verdict` widens ONLY the `test` kind's failure-streak limit by `EXPECT_RED_TEST_BONUS` (2) for that agent — `edit`/`bash` limits are unaffected. Deliberate TDD red runs do not trip the streak at the same threshold as a genuinely broken change.
- Budget-exhausted denial message names both remedies: relaunch with a bigger `[swe-budget: N]` next time, or lift the current trip now with SendMessage containing `[scope-extend: N]`.
- Orchestrator lifts a trip with SendMessage containing `[scope-extend]` or `[scope-extend: N]` (+N calls, default 30; resets all streaks) — logged by `swe_post_orchestrator_drift.py` as `scope_extend`.
