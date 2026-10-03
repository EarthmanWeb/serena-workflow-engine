---
name: DOM_SWE_HOOKS_PRE_GATES
description: PreToolUse gatekeeper hub — init gate, memory-fs gate, edit validation, memory index gate, bash test gate, read guard, question consent gate, agent model gate.
obligations:
  - Init gate blocks ALL tools until the WF_INIT chain completes; `swe_pre_memory_fs_gate.py` DENIES Bash/Grep/Glob/Read on Serena memory stores for both main agent and subagents. Full detail: `mem:dom/DOM_SWE_HOOKS_PRE_GATES_INIT_FS`.
  - `[doc-gate]` in `swe_pre_edit_validate.py` is MAIN-AGENT-ONLY doc enforcement; `swe_pre_read_guard.py` DENIES an unwindowed Read of a large code file for BOTH main agent and subagents. Full detail: `mem:dom/DOM_SWE_HOOKS_PRE_GATES_DOCS`.
  - `swe_pre_agent_model_gate.py` runs five DENY checks plus the non-denying `[sweep-gate]` auto-inject and budget/scope-gate stamping on every Agent/Task call. Full detail: `mem:dom/DOM_SWE_HOOKS_PRE_GATES_AGENT`.
  - `swe_pre_memory_index_gate.py` HARD-DENIES spec/report/research/project links into MEMORY.md and any dom/ref/dev/feature memory write with no `obligations:` field.
  - `swe_pre_bash_test_gate.py` gates ONLY the main agent on TEST docs for detected test-runner commands; subagent TEST-doc reading is enforced at delegation time via `[sweep-gate]`.
  - `swe_pre_question_consent_gate.py` DENIES `AskUserQuestion` while `blanket_consent` is set in WM, except in `WF_DONE`; `auto_approve: true` never denies it.
  - `swe_pre_browser_repro_gate.py` DENIES Bash E2E reruns and Agent/Task E2E rerun-delegation once an `e2e_fail` stream event has no later `browser_repro` event — for both main agent and spawned agents. `BROWSER_REPRO_NA=1` in the Bash command escapes a genuinely non-browser (pure REST/CLI) spec; no escape exists for the Agent/Task path.
metadata:
  type: domain
---

# DOM_SWE_HOOKS_PRE_GATES — Pre-Tool Gatekeepers (Hub)

Hub: `mem:dom/DOM_SWE_HOOKS`.

This memory is a split hub. Read a child per the routing table below for full detail on its gate(s); this file holds only the invariants needed on every read.

## Routing Table

| When                                                                                         | Read                                      |
| -------------------------------------------------------------------------------------------- | ----------------------------------------- |
| Debugging/editing the init gate (two-tier breaker, sentinel recovery) or the memory-fs gate  | `mem:dom/DOM_SWE_HOOKS_PRE_GATES_INIT_FS` |
| Debugging/editing `[doc-gate]` (edit-time doc enforcement) or the large-code-file Read guard | `mem:dom/DOM_SWE_HOOKS_PRE_GATES_DOCS`    |
| Debugging/editing the agent model gate, `[sweep-gate]`, scope budget/stamping                | `mem:dom/DOM_SWE_HOOKS_PRE_GATES_AGENT`   |
| Editing memory-index enforcement, bash-test gate, or question-consent gate                   | Stay in this hub — see sections below     |

## `swe_pre_edit_validate.py` — PreToolUse (Edit/Write/Serena)

- Block edits in planning states (WF_VERIFY is edit-allowed); in execution states DENY until the per-task sweep sentinel exists (WF_CLASSIFY 4d/4e verified).
- Test-artifact edits additionally require `dev/DEV_TESTS` + `feature/FEATURE_TESTS` docreads when those memories exist.
- **HARD BLOCK** (delegation economics): denies further main-agent edits at ≥12 consecutive undelegated task-work calls (`DRIFT_HARD_THRESHOLD`, tracked by `swe_post_orchestrator_drift.py`, see `mem:dom/DOM_SWE_HOOKS_POST`). Cleared by a BACKGROUND Agent/Task delegation (`run_in_background: true`) or any Workflow call — a foreground Agent/Task call does NOT clear it — or by recording `single-agent: <reason>` in WM `## Workflow Context` (tight single-file coupled-fix exception only, per `mem:feature/FEATURE_SUBAGENTS`).
- Drift-block exemption ONLY — exempt for spawned-agent tool calls on the HARD BLOCK check above; the block applies to the main orchestrator agent only, never to a subagent already doing delegated work.
- `[doc-gate]` enforcement detail (required-docs mapping, fallback, Bash-write-as-edit handling): `mem:dom/DOM_SWE_HOOKS_PRE_GATES_DOCS`.

## `swe_pre_memory_index_gate.py` — PreToolUse (Edit/Write/write_memory/edit_memory)

- HARD-DENY spec/report/research/project links entering MEMORY.md (state-independent; the post-hook only advises).
- ALSO DENIES a `write_memory`/direct-`Write` that creates or overwrites a dom/ref/dev/feature memory with no `obligations:` field (`obligations: []` passes; `edit_memory` partial edits exempt) — Change Set H, see `mem:ref/REF_MEMORY_STYLE`.
- `[site-data]` — denies `write_memory`/`edit_memory`/memory-tree `Edit`/`Write` whose content carries non-placeholder IPv4 (loopback + RFC5737 allowed), non-placeholder emails, credentialed URLs, SSH connect strings, private-key blocks, or token prefixes. No escape. Rule source `mem:ref/REF_NO_SITE_DATA`.

## `swe_pre_bash_test_gate.py` — PreToolUse (Bash)

Validate test commands against WF_DEBUG_TDD.

- Detected test runners: `unittest`, `pytest`, `npm test`, `jest`, `vitest`, `playwright`, `phpunit`, `go test`, `cargo test`.
- Main agent: sentinel (read-once) behavior unchanged — a session-scoped `.test_feature_{session_id}` sentinel, created when `feature/FEATURE_TESTS` is read, clears the gate for the rest of the session.
- Subagents: EXEMPT from this gate — per-agent bash test gating is REMOVED. A subagent's TEST-doc reading requirement (`feature/FEATURE_TESTS` + `dev/DEV_TESTS` if present) is enforced once, at delegation time, by `[sweep-gate]` in `swe_pre_agent_model_gate.py` (`mem:dom/DOM_SWE_HOOKS_PRE_GATES_AGENT`), not per Bash call.

## `swe_pre_question_consent_gate.py` — PreToolUse (AskUserQuestion)

Deny questions while `blanket_consent` is set in WM (override tag for destructive/scope changes). `auto_approve: true` (WF_CLASSIFY 2b plan-approval skip) NEVER denies AskUserQuestion.

- Pure fn `question_denied(blanket_consent, current_state, tool_input)` — True only when consent is set, state is NOT `WF_DONE`, and the call lacks `[consent-override]`.
- ALLOW in `WF_DONE` regardless of consent — the completion round asks every `— deferred: chose <X>` Open Decisions entry queued under consent. State read via `StateManager(cwd, session_id).get_current_state()`.
- Deny message instructs: pick the most logical option, act, record `- [ ] <decision> — options: A | B — deferred: chose <A>` in WM `## Open Decisions`.
- Flag lifetime = ONE task: `core.session.clear_blanket_consent(cwd, session_id)` rewrites both flags to `false` (atomic tmp + `os.replace`); `StateManager.transition_to` calls it on WF_CLASSIFY re-entry from a later state (see `mem:dom/DOM_SWE_STATE_MACHINE` Transition Side-Effects).

## `swe_pre_browser_repro_gate.py` — PreToolUse (Bash, Agent|Task)

Browser-repro-first gate (incident 2026-10-02: 4+ rerun cycles on unverified theories after an E2E failure, never reproduced in the browser). Pure helpers in `core/browser_repro.py`.

- `core.browser_repro.needs_browser_repro(events)` reads the WHOLE session stream: True iff the last `e2e_fail` event is AFTER the last `browser_repro` event (either event may carry any `agent` — a repro from ANY agent satisfies the requirement for everyone).
- `e2e_fail` is recorded from TWO places — a crashed (nonzero-exit) E2E Bash command reaches `swe_post_tool_failure.py` (PostToolUseFailure); an E2E run redirected to a log (`... ; echo exit $?`, exit 0 at the shell level) is caught instead by `swe_post_doc_claims.py` (PostToolUse: Bash) reading the captured output for `core.browser_repro.is_failed_e2e_output` (a `\d+ failed` summary or a nonzero `exit N` marker). The doc-claims hook records `e2e_fail` for a spawned agent too (checked BEFORE that hook's own orchestrator-WM-only early return).
- `browser_repro` is recorded by `swe_post_browser_repro.py` (PostToolUse: `mcp__browser-devtools__.*`) on any ACTUAL repro-step tool (`core.browser_repro.is_browser_repro_tool`: navigation__/interaction__/a11y__/content__/o11y_*/scenario-run/execute) — NOT the scenario-catalog tools (scenario-list/-search/-add/-delete/-update).
- Deny check 1 (Bash): `core.browser_repro.is_e2e_command(command)` (playwright test / run-test-single.sh / `npm run *:t` / `npm run demo1[:project]` — the last two are the Convenely plugin-repo runners) AND `needs_browser_repro` → deny, UNLESS the command carries `BROWSER_REPRO_NA=1` (asserts a non-browser pure REST/CLI spec).
- Deny check 2 (Agent|Task): `core.browser_repro.is_e2e_delegation(prompt)` (mentions playwright/`.spec.ts`/run-test-single/demo1:t/npm run demo1) AND `needs_browser_repro` → deny. No escape prefix on this path — a genuinely non-browser rerun goes through Bash with `BROWSER_REPRO_NA=1`, not through a delegated agent swapping the requirement.
