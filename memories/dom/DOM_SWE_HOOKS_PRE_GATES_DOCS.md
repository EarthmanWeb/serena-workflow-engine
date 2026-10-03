---
name: DOM_SWE_HOOKS_PRE_GATES_DOCS
description: Doc-gate (edit-time doc enforcement) and the large-code-file Read guard.
metadata:
  type: domain
obligations:
  - doc-gate DENIES a main-agent edit until every memory required_docs_for_path names for the target is read this session.
  - read_guard DENIES a Read with no offset/limit on a code file over 300 lines; fails open on error; no subagent exemption.
  - required_docs_for_path falls back to dev/DEV_<LANG> by file extension + feature/FEATURE_DEV_STANDARDS when no paths:-matched memory names a dev/* doc; plugin-shipped memories/ paths: globs apply only inside the plugin's own source repo.
  - A Bash command that writes into the project (outside .serena/**/.git/**) gets the FULL edit gate (planning-state, sweep, doc-gate, drift) per in-project write target memory_fs.bash_write_targets detects; a non-writing Bash call is a silent no-op.
---

# DOM_SWE_HOOKS_PRE_GATES_DOCS — Doc-Gate + Read Guard

Hub: `mem:dom/DOM_SWE_HOOKS_PRE_GATES`.

## No docs-first search gate

Grep/Glob/`search_for_pattern`/Bash-inspection calls are UNGATED — there is no pre-search docs budget or deny path for them, by design: a budget-and-refill gate taxes the Bash-grep path agents prefer 4:1 over Grep/Glob, and each refill costs a carried memory read for little denial yield. `_related_links`/`_search_credit`/`_unread_related` in `swe_post_read_state.py` feed the separate sweep/docpending system (`mem:dom/DOM_SWE_FEATURE_GATES`) and are unrelated to search gating.

## `swe_pre_read_guard.py` — PreToolUse (`Read`)

DENIES a `Read` with no `offset`/`limit` when the target is a CODE file (`.py .php .ts .tsx .js .jsx .scss .css .go .rb .java`) over `LARGE_FILE_LINES` (300) lines. Allows everything else — non-code files, small code files, any Read already passing offset/limit. Applies to BOTH main agent and spawned subagents, no exemption (pure cost control, no doc-discovery semantics). Fails open on any error. Measured basis: 10 full Reads >10k tok = 130k tok, 27% of all Read tokens in one transcript study. Deny message: use Grep -n to locate, then Read offset/limit (~80 lines). Tests: `tests/test_read_guard.py`.

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
