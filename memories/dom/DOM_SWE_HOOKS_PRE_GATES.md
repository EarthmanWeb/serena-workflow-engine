---
name: DOM_SWE_HOOKS_PRE_GATES
description: PreToolUse gatekeeper hooks — init gate (incl. two-tier circuit breaker + recovery), edit validation, memory index gate, bash test gate, docs-first search gate, question consent gate, agent model gate.
obligations:
  - Init gate blocks ALL tools until the WF_INIT chain completes; Tier-1/Tier-2 degraded modes never unlock Edit/Write/NotebookEdit/mutating Bash; exempt for spawned-agent tool calls.
  - Docs-first search gate DENIES gated calls once the `GATED_CALL_BUDGET` (15) is spent with no fresh `docread`; spawned agents are always exempt.
  - Agent model gate appends a `[swe-steering-contract]` clause via `updatedInput` on every ALLOW, declaring orchestrator SendMessage a trusted amendment and hook workflow banners orchestrator-only.
  - `[doc-gate]` in `swe_pre_edit_validate.py` DENIES a MAIN-AGENT edit until it itself has read every memory `doc_requirements.required_docs_for_path` names for the target file (SESSION-scoped reads, not per-task) — subagent enforcement is REMOVED from this gate; it moves to delegation time via `[sweep-gate]` in `swe_pre_agent_model_gate.py`.
  - `required_docs_for_path` falls back to `dev/DEV_<LANG>` by file extension + `feature/FEATURE_DEV_STANDARDS` when no `paths:`-matched memory names a `dev/*` doc; plugin-shipped `memories/` `paths:` globs apply only inside the plugin's own source repo.
  - A Bash command that writes into the project (outside `.serena/**`/`.git/**`) gets the FULL edit gate (planning-state, sweep, doc-gate, drift) per in-project write target `memory_fs.bash_write_targets` detects; a non-writing Bash call is a silent no-op.
  - `swe_pre_bash_test_gate.py` gates ONLY the main agent (sentinel/read-once behavior) on TEST docs for every detected test-runner command (unittest/pytest/npm test/jest/vitest/playwright/phpunit/go test/cargo test) — the per-agent subagent gating is REMOVED; a subagent's required test docs are enforced at delegation time via `[sweep-gate]` instead.
  - `swe_pre_agent_model_gate.py`'s `[sweep-gate]` check is NOT a deny — when the orchestrator-written prompt's "Required reading:" section is missing a name `delegation_sweep.required_reading(prompt, wm_text, project_root, cap=8)` computes as required, the gate AUTO-INJECTS the missing names into that section (`with_missing_required_reading`) and ALLOWS the call, surfacing which names it added via `permissionDecisionReason` — `[sweep-exempt: <reason>]` still skips the computation entirely for trivial read-only tasks; on every ALLOW the gate appends a `[swe-required-reading]` block with each required memory's `obligations:` inline.
  - Init gate enforces `[scope-gate]` per spawned agent (test 2/edit 2/bash 3 failure streaks, tool-call budget; `test` limit widens by `EXPECT_RED_TEST_BONUS` (2) when the agent was spawned with `expect_red`); a trip restricts the agent to read-only tools until the orchestrator sends `[scope-extend]`.
  - `swe_pre_memory_fs_gate.py` DENIES Bash/Grep/Glob/Read access to Serena memory stores (`.serena/memory/`, `.serena/memories/`, the auto-memory symlink) for BOTH main agent and subagents — shell reads and shell content writes alike; exempt only for uninitialized/bypassed projects and the spawned `swe-init-agent`.
metadata:
  type: domain
---

# DOM_SWE_HOOKS_PRE_GATES — Pre-Tool Gatekeepers

Hub: `mem:dom/DOM_SWE_HOOKS`.

## `swe_pre_memory_fs_gate.py` — PreToolUse (Bash/Grep/Glob/Read)

Shared classifier: `hooks/swe_hooks/core/memory_fs.py` (`is_memory_store_path`, `bash_memory_access`, `tool_memory_access`).

- DENIES Bash/Grep/Glob/Read access to Serena memory STORES: `.serena/memory/`, `.serena/memories/`, and the `~/.claude/projects/<enc>/memory` auto-memory symlink — resolved via realpath so the symlink target is caught even when addressed through the link.
- Applies to BOTH the main agent AND subagents — no subagent-type exemption except the spawned `swe-init-agent` (`agent_type` check).
- Denies shell READS (cat/grep/rg/awk/sed/head/tail/ls/find/wc, Read/Grep/Glob tool calls) AND shell CONTENT WRITES into a memory path: redirection into a memory file, `tee`, `sed -i`, `perl -i`, an inline `python -c`/`node -e`/heredoc that touches a memory path.
- Exempt (NOT gated): project not initialized or bypassed (`core.config.resolve_setup_state` → `initialized` false, or `"bypass": true` in `swe-setup-complete.json`); `git`, `mkdir`, `ln`, `cp`, `mv`, `rm` targeting memory paths; running a script FILE (`python3 scripts/... --root .serena/memory`) — the gate inspects inline code, not script invocations; grepping plugin-SOURCE files for the literal string `.serena/memory` (text search over non-memory trees); `WM_*.md` session files; the plugin-source `memories/` tree of the plugin repo (not a Serena memory store — edited as plain files).
- Deny message routes each blocked intent to the Serena memory tool that replaces it: a name/keyword lookup → `read_memory`/`list_memories`/`search_memories_by_name`; a "what is this about" lookup → `search_memories_by_front_matter`; a body/content search → `mcp__plugin_swe_serena__search_for_pattern(substring_pattern=…, relative_path=".serena/memory")`; a write → `write_memory`/`edit_memory`; a WM read → `swe_wm_read`.
- `swe_pre_edit_validate.py`'s `_is_raw_memory_write` check now calls `memory_fs.is_memory_store_path` — symlink-aware, same resolution as this gate.
- `swe_pre_search_docs_gate.py` B2 credits a "memory-grep" docread ONLY for plugin-source `memories/` path segments — memory-STORE access passes through this gate with no `docread` event (denied here when gated, allowed through uncredited when exempt).
- Registered in `hooks/hooks.json` as matcher `Bash|Grep|Glob|Read`, directly after the init gate.

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
- Spawned agents: also enforces the `[scope-gate]` verdict from `hooks/swe_hooks/core/scope_guard.py` — a tripped agent (consecutive failure streak by kind: test 2, edit 2, bash 3; or tool-call budget exhausted) gets ONLY read-only tools (Read/Grep/Glob/Serena reads/memory reads/SendMessage); every spawned-agent tool call logs an `agent_call` event for streak/budget tracking.

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

### `[doc-gate]` — main-agent-only doc-read enforcement (edits)

- `doc_requirements.required_docs_for_path(file_path, project_root)` maps the edit target to its governing memories: every `feature/*`/`dev/*` memory whose front-matter `paths:` glob matches the file, PLUS `feature/FEATURE_TESTS` (+ `dev/DEV_TESTS` if present) when the target is a test artifact.
  - No `paths:`-matched memory names a `dev/*` doc (missing/no-front-matter dev-standards memory) → `doc_requirements.fallback_dev_docs(rel_path, project_root)` adds every existing `dev/DEV_<LANG>` candidate for the file's extension (`EXTENSION_LANGUAGE_FALLBACK`, longest suffix first, e.g. `.blade.php` before `.php`) PLUS `feature/FEATURE_DEV_STANDARDS` if it exists.
  - The plugin-shipped `memories/` root's `paths:` globs (e.g. FEATURE_SWE's `hooks/**`) apply ONLY when `project_root` IS the SWE plugin source repo itself — matched via `_is_plugin_source_repo` comparing `.claude-plugin/plugin.json` `name` against the shipped tree's own plugin.json. An unrelated project with a same-named directory (e.g. its own `hooks/`) is never told it needs FEATURE_SWE.
- DENY with `[doc-gate]` when ANY required memory is unread by the MAIN agent — checked via `collect_values_session(stream_path, agent_id=None)`, SESSION-scoped (NOT per-task): a FEATURE__/DEV__ memory read earlier in the session (an earlier task, a prior prompt) satisfies a later task's edit to the same path. Operator decision — dev-standards reads count per session.
- Subagent enforcement is REMOVED from this gate — a subagent's edits are NEVER checked here. Its required reading is enforced once, at delegation time, by `[sweep-gate]` in `swe_pre_agent_model_gate.py` (see below) — the orchestrator's prompt must already name every required memory before the subagent is spawned.
- Subagents face NO pre-edit doc gate — no sweep gate, no drift block, no workflow-state gate, no `[doc-gate]`. Its pre-edit surface is empty; its reading obligation is satisfied (or denied) once at spawn time.
- Bash writes into the project are treated as edits: `memory_fs.bash_write_targets(command)` extracts in-project write targets (redirects `>`/`>>`/`>|`/`&>`, `tee`, `sed`/`perl -i`, `cp`/`mv`/`install` destination incl. `-t DIR`, `touch`/`truncate`, `dd of=`, inline-interpreter writes via a write-indicator heuristic, `bash -c`/`sh -c`/`zsh -c` recursion), excluding `.serena/**`/`.git/**` (already gated by `swe_pre_memory_fs_gate.py`) and any path outside the project root. Each resolved target runs the SAME sweep/doc-gate/drift checks (same order) a direct Edit to that file would get, same main-agent/spawned-agent exemptions. A non-writing or out-of-project Bash call is a silent no-op — never blocked, never logged.
  - Known limitation: the shared pipe-split regex has no special case for `>|`'s bare `|` — `echo x >| a.txt` is split at that `|` before the clobber-redirect target is detected (same gap as the memory-fs gate's analogous case).
- `hooks.json` matcher for this hook now also covers `NotebookEdit`, `MultiEdit`, `Bash`, and the Serena `create_text_file`/`replace_lines`/`delete_lines`/`insert_at_line`/`replace_in_files` tools (both `mcp__plugin_swe_serena__` and `mcp__serena__` forms). Target-path extraction (`_extract_target_path`, single source of truth in this hook) resolves `file_path` (Edit/Write/MultiEdit) → `notebook_path` (NotebookEdit) → `relative_path` (Serena symbolic edit tools) — a `replace_in_files` target that is a directory or empty skips the doc-gate specifically but keeps state/sweep/drift checks.

## `swe_pre_memory_index_gate.py` — PreToolUse (Edit/Write/write_memory/edit_memory)

- HARD-DENY spec/report/research/project links entering MEMORY.md (state-independent; the post-hook only advises).
- ALSO DENIES a `write_memory`/direct-`Write` that creates or overwrites a dom/ref/dev/feature memory with no `obligations:` field (`obligations: []` passes; `edit_memory` partial edits exempt) — Change Set H, see `mem:ref/REF_MEMORY_STYLE`.
- `[site-data]` — denies `write_memory`/`edit_memory`/memory-tree `Edit`/`Write` whose content carries non-placeholder IPv4 (loopback + RFC5737 allowed), non-placeholder emails, credentialed URLs, SSH connect strings, private-key blocks, or token prefixes. No escape. Rule source `mem:ref/REF_NO_SITE_DATA`.

## `swe_pre_bash_test_gate.py` — PreToolUse (Bash)

Validate test commands against WF_DEBUG_TDD.

- Detected test runners: `unittest`, `pytest`, `npm test`, `jest`, `vitest`, `playwright`, `phpunit`, `go test`, `cargo test`.
- Main agent: sentinel (read-once) behavior unchanged — a session-scoped `.test_feature_{session_id}` sentinel, created when `feature/FEATURE_TESTS` is read, clears the gate for the rest of the session.
- Subagents: EXEMPT from this gate — per-agent bash test gating is REMOVED. A subagent's TEST-doc reading requirement (`feature/FEATURE_TESTS` + `dev/DEV_TESTS` if present) is enforced once, at delegation time, by `[sweep-gate]` in `swe_pre_agent_model_gate.py`, not per Bash call.

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

Deny questions while `blanket_consent` is set in WM (override tag for destructive/scope changes). `auto_approve: true` (WF_CLASSIFY 2b plan-approval skip) NEVER denies AskUserQuestion.

- Pure fn `question_denied(blanket_consent, current_state, tool_input)` — True only when consent is set, state is NOT `WF_DONE`, and the call lacks `[consent-override]`.
- ALLOW in `WF_DONE` regardless of consent — the completion round asks every `— deferred: chose <X>` Open Decisions entry queued under consent. State read via `StateManager(cwd, session_id).get_current_state()`.
- Deny message instructs: pick the most logical option, act, record `- [ ] <decision> — options: A | B — deferred: chose <A>` in WM `## Open Decisions`.
- Flag lifetime = ONE task: `core.session.clear_blanket_consent(cwd, session_id)` rewrites both flags to `false` (atomic tmp + `os.replace`); `StateManager.transition_to` calls it on WF_CLASSIFY re-entry from a later state (see `mem:dom/DOM_SWE_STATE_MACHINE` Transition Side-Effects).

## `swe_pre_agent_model_gate.py` — PreToolUse (Agent/Task)

Enforces orchestrator + swarm delegation with complexity-based model tiers. FIVE independent DENY checks, plus a non-denying `[sweep-gate]` auto-inject:

1. Missing `model` param — required for every subagent_type except fixed-model built-ins (`claude-code-guide`, `statusline-setup`).
2. Prompt lacks the subagent bypass marker ("BYPASS WF_INIT" / "you are a subagent" / "swarm agent") — without it the spawned agent re-runs the init chain.
3. `model: "opus"` on a routine-keyword prompt (tests/lint/grep/inventory/read-only audit) with no design keyword AND no complexity keyword — override via literal `[opus-justified: <reason>]` tag in the prompt (`[premium-justified: <reason>]` accepted as an alias, same requirement). Design keywords: novel architecture/design, broad refactor. Complexity keywords: debug, root cause, security, auth, concurrency, race, deadlock, state machine, cross-file, cross-system, regression, flaky — either set overrides the routine-keyword deny; the denial message leads with the justify-tag option before any other remedy.
4. `model: "fable"` on ANY subagent call — fable is NEVER delegated by default, regardless of task shape — override via literal `[fable-justified: <reason>]` tag (`[premium-justified: <reason>]` alias also accepted).
5. `run_in_background` missing or `false` on ANY Agent/Task call with no literal `[foreground-justified: <reason>]` tag in the prompt — background is the DEFAULT and REQUIRED value; no subagent_type exemption.

`[sweep-gate]` is not a deny check — `_missing_sweep_names(prompt, required)` computes `required = delegation_sweep.required_reading(prompt, wm_text, project_root, cap=8)` and subtracts names already present in the orchestrator-written prompt (`[sweep-exempt: <reason>]` short-circuits to `[]`). Any names still missing are auto-injected into the prompt's "Required reading:" section via `with_missing_required_reading` (idempotent — a name already present anywhere in the prompt is never re-added) and the call is ALLOWED, with `permissionDecisionReason` naming which memories were auto-added (`📋 [sweep-gate] auto-added required reading: <names>`). `missing_sweep_reason` is the pure "what would be missing" message-builder (used by tests and by the auto-inject path).

Rationale: the orchestrator already runs the premium model; delegation moves work OFF it. Check 5's rationale: a foreground delegation blocks the orchestrator on one call with no parallelism and does not reset the drift counter (`mem:dom/DOM_SWE_HOOKS_POST`). `[sweep-gate]`'s rationale: the subagent's own `[doc-gate]`/per-agent bash-test gating are enforced only at the main agent (see `swe_pre_edit_validate.py` and `swe_pre_bash_test_gate.py` sections above) — required reading for a subagent is enforced ONCE, at spawn time, by injecting it into the prompt rather than by forcing a relaunch round-trip.

### `delegation_sweep.required_reading` — sources, cap, idempotence

`hooks/swe_hooks/core/delegation_sweep.py` computes the sweep from THREE sources, capped at 8 memory names total:

1. `FEATURE_*`/`DEV_*` memories whose front-matter `paths:` glob matches a file path named in the prompt.
2. `feature/FEATURE_TESTS` + `dev/DEV_TESTS` (when present) for any prompt describing test work.
3. The orchestrator WM's `**Memories loaded**`, `**Rules planned**`, and `## Compliance Checklist` `(mem:…)` citations — excluding `wf/*`, `claude/*`, `WM_*`, and `spec/`/`report/`/`research/`/`project/` names.

On ALLOW, the gate appends a `[swe-required-reading]` block listing `read_memory("<name>")` per required memory PLUS that memory's front-matter `obligations:` inline — the subagent has the rules before it calls `read_memory` itself. Idempotent via a marker (never appended twice to the same prompt). Fails open: a `delegation_sweep` error never blocks the Agent call — treat `required_reading` as returning `[]` on internal failure, same as any other gate exception in this hook.

On ALLOW, the gate appends a `[swe-steering-contract]` clause to the Agent call's prompt via `updatedInput` (pure fn `with_steering_clause`) — declares that a follow-up SendMessage from the launching orchestrator is a trusted amendment (may narrow/expand/redirect scope, including read-only → implementation) and that hook workflow banners (ON STEP/CONTINUE/WF_*) surfaced during the run target the orchestrator, never the spawned agent. The same clause tells the subagent that `[doc-gate]` denials ARE addressed to IT (not the orchestrator): read each memory the denial names with `read_memory` before editing or running tests — the orchestrator's reads never count for the subagent. Applies to every passing call; never applied on a DENY.

Pure functions `missing_model_reason`/`missing_bypass_marker_reason`/`opus_on_routine_reason`/`fable_without_justification_reason`/`foreground_without_justification_reason`/`missing_sweep_reason`/`with_steering_clause` are unit-tested.

### `doc_requirements.memory_roots` — plugin-source inclusion

`memory_roots(project_root)` also includes the plugin's shipped `memories/` root (not only `.serena/memory-paths.conf` entries) — `delegation_sweep.required_reading`'s FEATURE__/DEV__ path-match and FEATURE_TESTS/DEV_TESTS lookups resolve against BOTH the plugin source tree and this repo's local dev memories. A required memory that exists only in `memories/` (plugin source, ships to every installed repo) is named correctly, never silently dropped for living outside `.serena/memory/` (this repo's local-only dev memories).

### Budget tag stamping + clause SCOPE rule

- On ALLOW, the gate stamps a `[swe-budget: N]` tag onto the spawned agent's tool-call budget by model: haiku 25, sonnet 60, opus 120, fable 120. The orchestrator MAY set its own tag in the prompt to override the default.
- The auto-appended steering clause carries a SCOPE rule: do only the stated task; on a failure the agent did not cause, or after 2 failed attempts at its own change, STOP and report (what failed, evidence, hypothesis, what was not tried); NEVER debug/refactor/expand scope unless the orchestrator says so via SendMessage.
- `[scope-gate]` (`hooks/swe_hooks/core/scope_guard.py`) enforces this budget and per-kind failure streaks (test 2, edit 2, bash 3, each reset by a same-kind success) at `swe_pre_tool_init_gate.py` for every spawned-agent tool call. A trip restricts the agent to read-only tools (Read/Grep/Glob/Serena reads/memory reads/SendMessage); the denial message says STOP and report.
- `scope_guard.expects_red_runs(prompt)` — true on a literal `[swe-expect-red]` tag or fail-proofing/red-green phrasing (`fail-proof`, `flip the assertion`, `expected-red`, `red-green`, `prove the test fails`, `intentionally failing`) in the SPAWNING prompt. When true, `agent_spawn` carries `expect_red: true` and `scope_verdict` widens ONLY the `test` kind's failure-streak limit by `EXPECT_RED_TEST_BONUS` (2) for that agent — `edit`/`bash` limits are unaffected. Deliberate TDD red runs do not trip the streak at the same threshold as a genuinely broken change.
- Budget-exhausted denial message names both remedies: relaunch with a bigger `[swe-budget: N]` next time, or lift the current trip now with SendMessage containing `[scope-extend: N]`.
- Orchestrator lifts a trip with SendMessage containing `[scope-extend]` or `[scope-extend: N]` (+N calls, default 30; resets all streaks) — logged by `swe_post_orchestrator_drift.py` as `scope_extend`.

## Spawned-agent exemptions vs per-agent gating

- `swe_pre_tool_init_gate.py`: exempt for spawned-agent tool calls — a subagent bypasses the init chain entirely per its prompt marker, not per this gate; the bypass guard (marker detection) and Serena session metadata (`agent_id`/`agent_type`) still apply to identify the call as spawned.
- `swe_pre_bash_test_gate.py`: EXEMPT for spawned-agent Bash calls — per-agent TEST-doc gating is REMOVED; a subagent's TEST-doc requirement is enforced once, at delegation time, by `[sweep-gate]`.
- `swe_pre_edit_validate.py`: EXEMPT for spawned-agent edits — `[doc-gate]` is now MAIN-AGENT-ONLY; a subagent's `doc_requirements` are enforced once, at delegation time, by `[sweep-gate]` (see `swe_pre_agent_model_gate.py` section above), not per edit inside the subagent's own run. The drift-block/sweep-sentinel checks in this gate remain main-agent-only as before.
- `swe_pre_agent_model_gate.py`: applies ONLY to the orchestrator's Agent/Task call, never to a spawned agent's own tool calls — `[sweep-gate]` is where subagent doc/test-reading enforcement now lives, entirely at spawn time.
- `swe_pre_memory_fs_gate.py`: NOT exempt for subagents — applies to every spawned agent's Bash/Grep/Glob/Read calls same as the main agent. The ONLY agent-type exemption is the spawned `swe-init-agent` (bootstrap needs direct memory-path access before the Serena memory store exists).
