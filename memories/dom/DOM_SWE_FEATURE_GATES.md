---
name: DOM_SWE_FEATURE_GATES
description: Feature-gate mechanism (sentinel-based tool blocking) and the sweep gate — per-task Feature Knowledge Sweep verification, two-tier dispositions, task-boundary/docpending windows.
obligations:
  - A docpending link surfaced by the PRIMARY feature is satisfied by read, planned (obligations cited as `(mem:<name>)` in the WM Compliance Checklist), or ruled out (with reason) — bare deferral is rejected.
  - `**Rules planned**:` names MUST each be cited as `(mem:<name>)` on a `## Compliance Checklist` line — an uncited planned name or an unmatched citation is rejected.
  - `doc-gate` DENIES any edit, by the main agent OR a subagent, until the CALLING agent has itself read every memory `doc_requirements.required_docs_for_path` names for the target file — scoped per-agent, never satisfied by another agent's reads.
metadata:
  type: domain
---

# DOM_SWE_FEATURE_GATES

## Feature Gate Pattern

Feature gates block specific tools until the relevant FEATURE_* memory is read. All gates use session-scoped sentinel files for O(1) checks.

### Mechanism

1. Pre-tool hook checks sentinel `.serena/streams/.{gate}_feature_{session_id}`.
2. Missing → block with instruction to read the FEATURE_* memory.
3. `swe_post_read_state.py` creates the sentinel via `create_feature_sentinel(session_id, gate_name)`.
4. Subsequent tool calls pass instantly (file-existence check).

### Registered Gates

| Gate Name  | Pre-Hook                    | Blocks                                                                       | Sentinel                     | Feature Memory                                                 |
| ---------- | --------------------------- | ---------------------------------------------------------------------------- | ---------------------------- | -------------------------------------------------------------- |
| `test`     | `swe_pre_bash_test_gate.py` | unittest/pytest/npm test/jest/vitest/playwright/phpunit/go test/cargo test   | `.test_feature_{session}`    | FEATURE_TESTS — main agent sentinel-gated; subagents per-agent |
| `sweep`    | `swe_pre_edit_validate.py`  | ALL edits in execution states                                                | `.sweep_feature_{session}`   | (WM-verified, not read-created — see below)                    |
| `doc-gate` | `swe_pre_edit_validate.py`  | ANY edit (main agent AND subagents) to a path with unread governing memories | none — checked live per call | `doc_requirements.required_docs_for_path(file, root)`          |

### The `doc-gate` Gate (per-agent, no sentinel)

Unlike `test`/`sweep`, `doc-gate` never caches a pass into a sentinel file — it re-checks `required_docs_for_path` against the CALLING agent's own docreads on every edit.

- `required_docs_for_path` = every `feature/*`/`dev/*` memory whose front-matter `paths:` glob matches the target file, PLUS `feature/FEATURE_TESTS` (+ `dev/DEV_TESTS` if present) when the target is a test artifact.
- Read-scope is per-agent: `collect_values_since_task_start(stream_path, agent_id=...)` — `agent_id=None` for the main agent, the subagent's own id (stamped by `swe_post_read_state.py`) for a subagent. One agent's docread NEVER clears another agent's `doc-gate`.
- Applies to a subagent's edits even when the orchestrator has already read the governing memory — the subagent MUST read it itself in its own session.

### Adding a New Gate

1. Create pre-hook `hooks/pre/swe_pre_{name}_gate.py` — check sentinel, block if missing.
2. In `swe_post_read_state.py`, call `create_feature_sentinel(session_id, '{gate_name}')` when FEATURE_* is read.
3. Register in `hooks/hooks.json`.
4. Add a directive to the FEATURE_* memory documenting the gate.

## The `sweep` Gate (per-task, WM-verified)

Unlike read-created gates, the sweep sentinel is created ONLY by the WM server: an `Affected Features` write whose `**Memories loaded**:` list is verified against the SESSION's actual named `docread` events (`_check_memory_sweep` in `wm_server.py`).

- D2 idempotence: a read from any earlier turn/task this session counts — re-listing without re-reading passes.
- List parsing: FIRST whitespace token per comma-separated entry (annotation text stripped).
- Workflow-machinery names (`wf/*`, `claude/*` — read before the task boundary) are IGNORED, not rejected; a list of ONLY machinery names still fails.
- Every transition INTO WF_CLASSIFY deletes the sentinel (`clear_sweep_sentinel` in `state_manager.py`) — same-session follow-up tasks MUST re-WRITE the Affected Features section before their first edit, but NEVER re-READ memories already read this session.
- Contract: `wf/WF_CLASSIFY` Steps 4d/4e. Tests: `tests/test_sweep_gate.py`.

### Two-Tier Sweep Dispositions (Change Set H)

A docpending link a task surfaces satisfies verification via loaded ∪ deferred ∪ planned ∪ ruled-out — not loaded-or-deferred alone.

- `**Rules planned**:` names MUST each be cited as `(mem:<name>)` on a `## Compliance Checklist` line — WM server REJECTS the write on an uncited planned name or a checklist citation with no matching planned name.
- `**Rules ruled out**:` entries REQUIRE a mandatory reason per name.
- See `mem:wf/WF_CLASSIFY` Step 4d (Tier 0 digest pass / Tier 1 body pass) and Step 4e (WM grammar).

### Task Boundary

"This task" = events since the last task boundary in the stream: the last `session_start` event or `state` event with `to_s=WF_CLASSIFY` (`events_since_task_start` in `core/stream.py`).

- Boundaries are stamped ONLY at genuine task starts — the prompt hook's new_task / after-WF_DONE transitions (`append_task_boundary`) and first-time session creation.
- Continuation/unclear prompts and mid-session slash commands (FAST TRACK re-invocation) NEVER stamp — a task's docreads keep counting across interleaved prompts.
- See `mem:dom/DOM_SWE_HOOKS_PROMPT_ROUTING` "Task-Boundary Stamping".

### Docpending Window (narrower than the task window)

A SUCCESSFUL sweep stamps a `sweep` marker; `_check_memory_sweep` accounts docpending links via `events_since_task_start(since_sweep=True)` — only links surfaced AFTER the last passed sweep.

- Consequence: once a sweep passes, its links are settled — a later sweep in the same session (common when continuation/pivot prompts don't re-stamp a task boundary) never re-demands a prior task's already-handled links.
- Docread/`Memories loaded` verification uses the FULL SESSION stream (D2).
- Leaked truncated link tokens (e.g. `ref/ref_...` from a clipped hook message) are dropped by `is_valid_memory_name()` before they can be demanded.
