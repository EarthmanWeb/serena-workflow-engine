---
name: DOM_SWE_HOOKS_PRE_GATES
description: PreToolUse gatekeeper hooks — init gate (incl. two-tier circuit breaker + recovery), edit validation, memory index gate, bash test gate, docs-first search gate, question consent gate, agent model gate.
obligations:
  - Init gate blocks ALL tools until the WF_INIT chain completes; Tier-1/Tier-2 degraded modes never unlock Edit/Write/NotebookEdit/mutating Bash; exempt for spawned-agent tool calls.
  - Docs-first search gate DENIES gated calls once the `GATED_CALL_BUDGET` (15) is spent with no fresh `docread`; spawned agents are always exempt.
  - Agent model gate appends a `[swe-steering-contract]` clause via `updatedInput` on every ALLOW, declaring orchestrator SendMessage a trusted amendment and hook workflow banners orchestrator-only.
  - `[doc-gate]` in `swe_pre_edit_validate.py` DENIES any edit — main agent AND subagents — until the CALLING agent itself has read every memory `doc_requirements.required_docs_for_path` names for the target file; a subagent is scoped to ITS OWN docreads only, never the orchestrator's.
  - `swe_pre_bash_test_gate.py` gates subagents per-agent on TEST docs for every detected test-runner command (unittest/pytest/npm test/jest/vitest/playwright/phpunit/go test/cargo test) — the prior blanket subagent exemption is REMOVED; only the main agent keeps sentinel (read-once) behavior.
metadata:
  type: domain
---

# DOM_SWE_HOOKS_PRE_GATES — Pre-Tool Gatekeepers

Hub: `mem:dom/DOM_SWE_HOOKS`.

## `swe_pre_tool_init_gate.py` — PreToolUse (all tools)

Block ALL tools until WF_INIT chain complete. TWO-TIER circuit breaker, both clearing on the next docread.

- **Tier 1 "recovery"** (3+ consecutive init denies with no docread, no `mcp_unavailable`): Serena may still be reachable — unlocks ONLY recovery/diagnostic Bash: `claude mcp list`/`get`, `ps`/`pgrep`, restricted log reads under `~/Library/Caches/claude-cli-nodejs/`, `~/.cache/claude-cli-nodejs/`, `~/.serena/logs/`, project `.serena/`, plus `--reset-sentinel`. NEVER Read/Grep/Glob the codebase.
- **Tier 2 "degraded"** (an `mcp_unavailable` event from `PostToolUseFailure` on a genuine Serena connection failure): unlocks Read/Grep/Glob/LS/ToolSearch + hardened read-only Bash.
- Edits/Write/NotebookEdit/mutating Bash stay denied in BOTH tiers.
- Hardened Bash classifier rejects: backtick/`$()`/`<()`/`>()`/redirection (except `2>/dev/null`, `2>&1`)/`tee`/`xargs`/`-exec`/`-execdir`/`-delete`/`sed -i`/`perl -i`. Every `;`/`&&`/`||`/`&`/pipe-stage's primary command must be in the allowlist. Excludes `python3 -m unittest`/`pytest` (execute code). git limited to `status`/`log`/`diff`/`show`/`branch`/`rev-parse` without `-c`/`--output`/`-o`.
- Events emitted: `init_deny`, `degraded`, `mcp_unavailable`.
- Allowed pre-init: `read_memory` (wf/* and init-chain), `write_memory`, `edit_memory`, `list_memories`, swe_wm tools, `ToolSearch`, Serena project-setup tools.
- Blocked pre-init: `Bash`, `Grep`, `Glob`, `Edit`, `Write` (non-WM), `find_symbol`, `get_symbols_overview`, all other tools.
- Sentinel on entry to WF_CLASSIFY unlocks all tools for the session.

### Sentinel Recovery (self-healing)

Recreate a missing sentinel automatically when a valid WM exists for the session — prevents deadlock on mid-session pivots where the daemon blocks re-running the init chain but the gate demands it.

Recovery points, checked in order:

1. `swe_user_prompt_workflow.py` — create sentinel when WM valid but sentinel missing, before any tool call.
2. `swe_pre_tool_init_gate.py` — WM-based fallback when the prompt hook did not fire or failed.

### Manual Reset

- One session: `python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel <session_id>`.
- ALL sentinels (next init chain recreates them): `python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel`.

## `swe_pre_edit_validate.py` — PreToolUse (Edit/Write/Serena)

- Block edits in planning states (WF_VERIFY is edit-allowed); in execution states DENY until the per-task sweep sentinel exists (WF_CLASSIFY 4d/4e verified).
- Test-artifact edits additionally require `dev/DEV_TESTS` + `feature/FEATURE_TESTS` docreads when those memories exist.
- **HARD BLOCK** (delegation economics): denies further main-agent edits at ≥12 consecutive undelegated task-work calls (`DRIFT_HARD_THRESHOLD`, tracked by `swe_post_orchestrator_drift.py`, see `mem:dom/DOM_SWE_HOOKS_POST`). Cleared by a BACKGROUND Agent/Task delegation (`run_in_background: true`) or any Workflow call — a foreground Agent/Task call does NOT clear it — or by recording `single-agent: <reason>` in WM `## Workflow Context` (tight single-file coupled-fix exception only, per `mem:feature/FEATURE_SUBAGENTS`).
- Drift-block exemption ONLY — exempt for spawned-agent tool calls on the HARD BLOCK check above; the block applies to the main orchestrator agent only, never to a subagent already doing delegated work.

### `[doc-gate]` — per-agent doc-read enforcement (ALL edits, main agent AND subagents)

- `doc_requirements.required_docs_for_path(file_path, project_root)` maps the edit target to its governing memories: every `feature/*`/`dev/*` memory whose front-matter `paths:` glob matches the file, PLUS `feature/FEATURE_TESTS` (+ `dev/DEV_TESTS` if present) when the target is a test artifact.
- DENY with `[doc-gate]` when ANY required memory is unread by the CALLING agent this task — checked via `collect_values_since_task_start(stream_path, agent_id=...)`.
- Per-agent scoping is load-bearing: `agent_id=None` counts ONLY main-agent docreads; a subagent's `agent_id` (from `core.session.get_agent_id`, stamped by `swe_post_read_state.py` on every subagent docread event) counts ONLY that subagent's own reads. The orchestrator's reads NEVER satisfy a subagent's `[doc-gate]`, and one subagent's reads never satisfy a sibling's.
- Subagents get ONLY this check — no sweep gate, no drift block, no workflow-state gate. `[doc-gate]` is the entire pre-edit surface a subagent faces.
- Remedy: `read_memory` each named memory (the subagent itself, not the orchestrator), then retry the edit. `swe_pre_agent_model_gate.py`'s steering clause tells every spawned agent this directly (see agent gate section below).

## `swe_pre_memory_index_gate.py` — PreToolUse (Edit/Write/write_memory/edit_memory)

- HARD-DENY spec/report/research/project links entering MEMORY.md (state-independent; the post-hook only advises).
- ALSO DENIES a `write_memory`/direct-`Write` that creates or overwrites a dom/ref/dev/feature memory with no `obligations:` field (`obligations: []` passes; `edit_memory` partial edits exempt) — Change Set H, see `mem:ref/REF_MEMORY_STYLE`.

## `swe_pre_bash_test_gate.py` — PreToolUse (Bash)

Validate test commands against WF_DEBUG_TDD.

- Detected test runners: `unittest`, `pytest`, `npm test`, `jest`, `vitest`, `playwright`, `phpunit`, `go test`, `cargo test`.
- Main agent: sentinel (read-once) behavior unchanged — a session-scoped `.test_feature_{session_id}` sentinel, created when `feature/FEATURE_TESTS` is read, clears the gate for the rest of the session.
- Subagents: gated PER-AGENT on TEST docs — the blanket subagent exemption is REMOVED. A subagent running a detected test command must itself have read `feature/FEATURE_TESTS` (+ `dev/DEV_TESTS` if present) this task, checked via `collect_values_since_task_start(agent_id=<this subagent's id>)`. The orchestrator's own FEATURE_TESTS read does NOT clear a subagent's gate.

## `swe_pre_search_docs_gate.py` — PreToolUse (Grep/Glob/search_for_pattern/Bash-inspection)

`Read` is NOT matched in hooks.json — `is_gated_call` never gates it, so excluding it from the matcher saves a hook subprocess per Read call.

- DOCS-FIRST blocking gate.
- Bash classification is by the PRIMARY (first pipe stage) command of each `;`/`&&`/newline group: work commands (test runners, builds, formatters, git commit) are NOT gated even when piped through head/tail/grep output filters; a sequenced `cat`/`grep` after a build IS gated (standalone recon).
- BUDGET model: one docs consult (`docread`) clears the next `GATED_CALL_BUDGET` (currently 15) gated calls; each allowed call appends a `gated` event; deny when the budget is spent or no `docread` exists. Clearance survives turn boundaries. Budget refill requires a FRESH docread (re-reads don't refill; credited memory searches always do).
- Deny message: budget refill ≠ completed research; lists pending related docs (docpending) as designated next reads; instructs write_memory backfill when discovery was required.
- Spawned agents are NEVER gated: the gate exempts them BEFORE any sentinel/budget check.
  - PRIMARY signal: `core.session.is_spawned_agent(input)` — a non-empty `agent_id`/`agent_type` in the hook payload (Claude Code stamps these ONLY on subagent tool calls; `session_id` is the SAME parent id for main + subagent, so it cannot discriminate).
  - FALLBACK: `core.session.is_subagent_transcript(transcript_path)` — the `<session>/subagents/agent-*.jsonl` shape, used when the payload carries the subagent's own path. Insufficient alone: the hook usually receives the PARENT transcript path for a subagent call, so `is_subagent_transcript` missed it and the subagent got gated on the parent's spent budget — hence the agent_id-first check.
- Undocumented area (no reasonable feature memories from both searches): deny message routes to a FOREGROUND Agent running `/swe-feature-onboard` (new area) or `/swe-feature-update` (stale docs) — `run_in_background: false` plus the literal `[foreground-justified: docs gate requires onboarding before search]` tag in the prompt, WAIT for completion, then read the memories it wrote to clear the gate. Manual grepping is NOT the remedy.

## `swe_pre_question_consent_gate.py` — PreToolUse (AskUserQuestion)

Deny questions while `auto_approve`/`blanket_consent` is set in WM (override tag for destructive/scope changes).

## `swe_pre_agent_model_gate.py` — PreToolUse (Agent/Task)

Enforces orchestrator + swarm delegation with complexity-based model tiers. FIVE independent DENY checks:

1. Missing `model` param — required for every subagent_type except fixed-model built-ins (`claude-code-guide`, `statusline-setup`).
2. Prompt lacks the subagent bypass marker ("BYPASS WF_INIT" / "you are a subagent" / "swarm agent") — without it the spawned agent re-runs the init chain.
3. `model: "opus"` on a routine-keyword prompt (tests/lint/grep/inventory/read-only audit) with no design/architecture keyword — override via literal `[opus-justified: <reason>]` tag in the prompt (`[premium-justified: <reason>]` accepted as an alias, same requirement).
4. `model: "fable"` on ANY subagent call — fable is NEVER delegated by default, regardless of task shape — override via literal `[fable-justified: <reason>]` tag (`[premium-justified: <reason>]` alias also accepted).
5. `run_in_background` missing or `false` on ANY Agent/Task call with no literal `[foreground-justified: <reason>]` tag in the prompt — background is the DEFAULT and REQUIRED value; no subagent_type exemption.

Rationale: the orchestrator already runs the premium model; delegation moves work OFF it. Check 5's rationale: a foreground delegation blocks the orchestrator on one call with no parallelism and does not reset the drift counter (`mem:dom/DOM_SWE_HOOKS_POST`).

On ALLOW, the gate appends a `[swe-steering-contract]` clause to the Agent call's prompt via `updatedInput` (pure fn `with_steering_clause`) — declares that a follow-up SendMessage from the launching orchestrator is a trusted amendment (may narrow/expand/redirect scope, including read-only → implementation) and that hook workflow banners (ON STEP/CONTINUE/WF_*) surfaced during the run target the orchestrator, never the spawned agent. The same clause tells the subagent that `[doc-gate]` denials ARE addressed to IT (not the orchestrator): read each memory the denial names with `read_memory` before editing or running tests — the orchestrator's reads never count for the subagent. Applies to every passing call; never applied on a DENY.

Pure functions `missing_model_reason`/`missing_bypass_marker_reason`/`opus_on_routine_reason`/`fable_without_justification_reason`/`foreground_without_justification_reason`/`with_steering_clause` are unit-tested.

## Spawned-agent exemptions vs per-agent gating

- `swe_pre_tool_init_gate.py`: exempt for spawned-agent tool calls — a subagent bypasses the init chain entirely per its prompt marker, not per this gate; the bypass guard (marker detection) and Serena session metadata (`agent_id`/`agent_type`) still apply to identify the call as spawned.
- `swe_pre_bash_test_gate.py`: NOT exempt for spawned-agent Bash calls running a detected test command — gated PER-AGENT on TEST docs (see section above). Non-test Bash calls from a subagent are unaffected by this gate.
- `swe_pre_edit_validate.py`: NOT exempt for spawned-agent edits — `[doc-gate]` applies to every caller, scoped per-agent (see section above). Only the drift-block/sweep-gate checks are main-agent-only.
