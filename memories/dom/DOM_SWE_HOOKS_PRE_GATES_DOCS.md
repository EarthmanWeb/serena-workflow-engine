---
name: DOM_SWE_HOOKS_PRE_GATES_DOCS
description: PreToolUse docs-first search gate — budget model, Bash primary-command classification, spawned-agent exemption, undocumented-area routing.
metadata:
  type: domain
obligations:
  - Docs-first search gate DENIES gated calls once the `GATED_CALL_BUDGET` (15) is spent with no fresh `docread`; spawned agents are always exempt.
  - On an undocumented area, route to a FOREGROUND `/swe-feature-onboard` or `/swe-feature-update` Agent call with `[foreground-justified: docs gate requires onboarding before search]` — never remedy by manual grepping.
  - `[doc-gate]` in `swe_pre_edit_validate.py` DENIES a MAIN-AGENT edit until it itself has read every memory `doc_requirements.required_docs_for_path` names for the target file (SESSION-scoped reads, not per-task) — subagent enforcement is REMOVED from this gate; it moves to delegation time via `[sweep-gate]`.
  - `required_docs_for_path` falls back to `dev/DEV_<LANG>` by file extension + `feature/FEATURE_DEV_STANDARDS` when no `paths:`-matched memory names a `dev/*` doc; plugin-shipped `memories/` `paths:` globs apply only inside the plugin's own source repo.
  - A Bash command that writes into the project (outside `.serena/**`/`.git/**`) gets the FULL edit gate (planning-state, sweep, doc-gate, drift) per in-project write target `memory_fs.bash_write_targets` detects; a non-writing Bash call is a silent no-op.
---

# DOM_SWE_HOOKS_PRE_GATES_DOCS — Docs-First Search Gate

Hub: `mem:dom/DOM_SWE_HOOKS_PRE_GATES`.

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

## `[doc-gate]` — main-agent-only doc-read enforcement (edits, in `swe_pre_edit_validate.py`)

- `doc_requirements.required_docs_for_path(file_path, project_root)` maps the edit target to its governing memories: every `feature/*`/`dev/*` memory whose front-matter `paths:` glob matches the file, PLUS `feature/FEATURE_TESTS` (+ `dev/DEV_TESTS` if present) when the target is a test artifact.
  - No `paths:`-matched memory names a `dev/*` doc (missing/no-front-matter dev-standards memory) → `doc_requirements.fallback_dev_docs(rel_path, project_root)` adds every existing `dev/DEV_<LANG>` candidate for the file's extension (`EXTENSION_LANGUAGE_FALLBACK`, longest suffix first, e.g. `.blade.php` before `.php`) PLUS `feature/FEATURE_DEV_STANDARDS` if it exists.
  - The plugin-shipped `memories/` root's `paths:` globs (e.g. FEATURE_SWE's `hooks/**`) apply ONLY when `project_root` IS the SWE plugin source repo itself — matched via `_is_plugin_source_repo` comparing `.claude-plugin/plugin.json` `name` against the shipped tree's own plugin.json. An unrelated project with a same-named directory (e.g. its own `hooks/`) is never told it needs FEATURE_SWE.
- DENY with `[doc-gate]` when ANY required memory is unread by the MAIN agent — checked via `collect_values_session(stream_path, agent_id=None)`, SESSION-scoped (NOT per-task): a FEATURE__/DEV__ memory read earlier in the session (an earlier task, a prior prompt) satisfies a later task's edit to the same path. Operator decision — dev-standards reads count per session.
- Subagent enforcement is REMOVED from this gate — a subagent's edits are NEVER checked here. Its required reading is enforced once, at delegation time, by `[sweep-gate]` in `swe_pre_agent_model_gate.py` (`mem:dom/DOM_SWE_HOOKS_PRE_GATES_AGENT`) — the orchestrator's prompt must already name every required memory before the subagent is spawned.
- Subagents face NO pre-edit doc gate — no sweep gate, no drift block, no workflow-state gate, no `[doc-gate]`. Its pre-edit surface is empty; its reading obligation is satisfied (or denied) once at spawn time.
- Bash writes into the project are treated as edits: `memory_fs.bash_write_targets(command)` extracts in-project write targets (redirects `>`/`>>`/`>|`/`&>`, `tee`, `sed`/`perl -i`, `cp`/`mv`/`install` destination incl. `-t DIR`, `touch`/`truncate`, `dd of=`, inline-interpreter writes via a write-indicator heuristic, `bash -c`/`sh -c`/`zsh -c` recursion), excluding `.serena/**`/`.git/**` (already gated by `swe_pre_memory_fs_gate.py`) and any path outside the project root. Each resolved target runs the SAME sweep/doc-gate/drift checks (same order) a direct Edit to that file would get, same main-agent/spawned-agent exemptions. A non-writing or out-of-project Bash call is a silent no-op — never blocked, never logged.
  - Known limitation: the shared pipe-split regex has no special case for `>|`'s bare `|` — `echo x >| a.txt` is split at that `|` before the clobber-redirect target is detected (same gap as the memory-fs gate's analogous case).
- `hooks.json` matcher for this hook now also covers `NotebookEdit`, `MultiEdit`, `Bash`, and the Serena `create_text_file`/`replace_lines`/`delete_lines`/`insert_at_line`/`replace_in_files` tools (both `mcp__plugin_swe_serena__` and `mcp__serena__` forms). Target-path extraction (`_extract_target_path`, single source of truth in this hook) resolves `file_path` (Edit/Write/MultiEdit) → `notebook_path` (NotebookEdit) → `relative_path` (Serena symbolic edit tools) — a `replace_in_files` target that is a directory or empty skips the doc-gate specifically but keeps state/sweep/drift checks.
