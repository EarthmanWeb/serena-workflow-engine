---
name: FEATURE_SWE
description: SWE plugin source layout, architecture, entry points, inventories. Hub for `mem:dom/DOM_SWE_*` children.
paths:
  - hooks/swe_hooks/**
  - hooks/pre/swe_*.py
  - hooks/post/swe_*.py
  - hooks/prompt/swe_*.py
  - hooks/session/swe_*.py
  - hooks/stop/swe_*.py
  - hooks/hooks.json
  - state-machine/states.json
  - skills/swe-*/**
  - commands/swe-*.md
obligations:
  - NEVER write to `.claude/plugins/serena-workflow-engine/` — it is the installed cache copy; this repo IS the plugin source, edit here.
  - Always pass `session_id` explicitly to `swe-wm` MCP tools — NEVER rely on most-recent-WM guessing across concurrent sessions.
metadata:
  type: feature
---

# FEATURE_SWE — Serena Workflow Engine

## Source Location (edit rules)

This repo IS the plugin source. `hooks/`, `memories/`, `skills/`, `commands/`, `state-machine/`, `scripts/`, `agents/` sit directly under the working-directory root — edit here. Target the repo root for ALL Serena/Glob/Grep searches. NEVER target or write to `.claude/plugins/serena-workflow-engine/` — it is the installed READ-ONLY cache copy. See `FEEDBACK_PLUGIN_SOURCE_LOCATION`. Type: plugin. Languages: Python/Bash/JSON/Markdown. Framework: Claude Code Plugins.

## Architecture Layers

State Machine (workflow FSM, `state-machine/`) · Core Modules (shared Python utils, `hooks/swe_hooks/core/`) · MCP Server (WM tools, `hooks/swe_hooks/mcp/`) · Hooks (event handlers, `hooks/{session,prompt,pre,post,stop}/`) · Skills (user-invocable workflows, `skills/`) · Commands (CLI shortcuts, `commands/`) · Memories (workflow docs, `memories/`) · Agents (subagent defs, `agents/`) · Scripts (build/deploy, `scripts/`).

### Data / State Flow

Flow: SessionStart → WF_INITIAL_SETUP (first time) or WF_INIT → WF_CLASSIFY → WF_ARCH_REVIEW → WF_EXECUTE ↔ WF_CHECKPOINT → WF_VERIFY → WF_DONE → WF_CLEANUP.

12 states: Setup (WF_INITIAL_SETUP, WF_ONBOARD) · Entry (WF_CLASSIFY, WF_CONTINUE) · Analysis (WF_RESEARCH, WF_RESEARCH_LITE) · Planning (WF_ARCH_REVIEW) · Gates (WF_CLARIFY) · Execution (WF_EXECUTE, WF_CHECKPOINT, WF_DEBUG_TDD) · Completion (WF_VERIFY, WF_DONE). FSM mechanics: `mem:dom/DOM_SWE_STATE_MACHINE`.

## Entry Points

Main: `state-machine/states.json` · Config: `.claude-plugin/plugin.json` · Hooks config: `hooks/hooks.json` · Init: `commands/swe-init.md`. Root files: `README.md`, `.mcp.json`, `.gitignore`.

## Core Modules (`hooks/swe_hooks/core/`)

`state_manager.py` (transitions/persistence) · `config.py` (paths, WM I/O) · `session.py` (session/WM mgmt) · `input.py`/`output.py` (hook I/O) · `stream.py` (JSONL event log) · `wm_validator.py` (WM validation) · `loop_guard.py` (`loopCaps` for `readAdvance` — refuse on cap exceeded, warn on oscillation) · `memory_size.py` (size thresholds; shared by `memory-size-audit.py`, `swe_post_memory_style.py`) · `memory_fs.py` (shared memory-store path/Bash classifier for `swe_pre_memory_fs_gate.py`, symlink-aware).

## MCP Server: swe-wm (`hooks/swe_hooks/mcp/`)

Stdlib-only stdio MCP server for WM updates; registered as `swe-wm`, started via `scripts/start-wm-mcp.sh`. Tools: `swe_wm_read` · `swe_wm_update` (CANONICAL — batched) · `swe_wm_update_section`/`swe_wm_update_status` (legacy) · `swe_wm_transition(session_id, target_state, reason, force=false)` — the ONLY MCP way to change Current State; validates against `states.json` (matrix, subflows rejected, loop caps unless `force=true`), shares `state_manager.perform_transition` with the `set_state.py` CLI. Protected: `Workflow Context`, `Transitions`. Session resolution: explicit param > `SWE_SESSION_ID` > `CLAUDE_SESSION_ID[:8]` > ERROR — NEVER most-recent-WM guessing.

## Hooks (21 scripts)

Hub: DOM_SWE_HOOKS (architecture/triggers/mechanics; children: PROMPT_ROUTING, PRE_GATES, POST, STOP, CORE_MODULES). Session: `swe_session_start.py`, `swe_session_end.py`. Prompt: `swe_user_prompt_workflow.py`, `swe_prompt_format_reminder.py`. Pre (8): init/memory-fs/edit/memory-index/bash-test/search-docs/question-consent/agent-model gates. Post (8): read-state, edit-checkpoint, search-docs-hint, todo-wm-sync, write-continue, memory-index, memory-style (`📏 MEMORY SIZE` advisory), tool-failure. Stop: `swe_stop_continue_working.py`, `swe_stop_response_format.py` (DOM_SWE_RESPONSE_FORMAT_GATE). Sweep gate: DOM_SWE_FEATURE_GATES.

## Skills (16), Commands (9), Agents (1)

Skills: `swe-feature-onboard`, `swe-feature-update`, `swe-gherkin-spec`, `swe-gherkin-dev`, `swe-memory-audit`, `swe-memory-frontmatter`, `swe-memory-obligations`, `swe-memory-size-audit` (split oversized memories into hub+children), `swe-scaffold-project`, `swe-symbol-index`, `swe-wm-update`, `swe-workflow-research`, `swe-workflow-arch-review`, `swe-workflow-debug-tdd`, `swe-workflow-verify`, `swe-wp-cli-setup`.

Commands: `/swe-init`, `/swe-status`, `/swe-reset`, `/swe-goto`, `/swe-bypass` (USER-ONLY), `/swe-cleanup`, `/swe-symlink-memory`, `/swe-memory-frontmatter`, `/swe-wp-cli-setup`. CLI: `swe_pre_tool_init_gate.py --reset-sentinel [session_id]` (deadlock recovery). Agent: `swe-init-agent`.

## Memories Organization

`memories/wf/` (WF_*.md) · `memories/ref/` (FEATURE_DEV_STANDARDS, REF_MEMORY_STYLE, etc.) · `memories/claude/` (CLAUDE.md, CLAUDE_OBLIGATIONS.md) · `memories/arch/` (ARCH_SWE.md) · `memories/dom/` (DOM_SWE_HOOKS+children, DOM_SWE_STATE_MACHINE, DOM_SWE_FEATURE_GATES, DOM_SWE_RESPONSE_FORMAT_GATE, DOM_SWE_BOOTSTRAP, DOM_SWE_MEMORY_PATHS) · `memories/feature/` (this file) · `memories/index/` (if any).

## Plan Mode Triggers

Always: WF_ARCH_REVIEW. Never: WF_DEBUG_TDD, WF_CHECKPOINT, WF_VERIFY, WF_DONE, WF_RESEARCH, WF_EXECUTE. Conditional: WF_CLASSIFY (complexity ≥ medium).

## Scripts

`bump-version.sh` · `install-hooks.sh` · `pre-commit` · `swe-bootstrap.py` (bootstrap — `mem:dom/DOM_SWE_BOOTSTRAP`) · `start-serena.sh` · `start-wm-mcp.sh` · `serena_memory_patch.py` (`mem:dom/DOM_SWE_MEMORY_PATHS`) · `validate-graph.py` (validate states.json: transitions, `transitionMatrix`, `rank`, `loopCaps`, `subflows`) · `skills/swe-memory-size-audit/scripts/validate-memory-graph.py` (bundled with the skill; dangling/orphan refs; pass ALL roots in one run; exit 1 on dangling) · `memory-size-audit.py` (sizes: ok ≤8,000/warn ≤16,000/split/unreadable ≥50,000 chars; `[--root [alias=]DIR] [--topic P] [--json]`, exit 1 on split/unreadable).

## Dependencies

Serena MCP (memory), swe-wm MCP (WM updates), jq, bash, python3.

### Serena MCP = OUR fork (em-serena)

- NEVER call Serena "third-party" or "upstream-only". We own it: repo `EarthmanWeb/serena`, local checkout `../em-serena` (sibling of this repo), branch `swe`.
- `scripts/start-serena.sh` runs `git+https://github.com/EarthmanWeb/serena@<sha of ref swe>` (override: `SWE_SERENA_REF`, `SWE_SERENA_NO_REFRESH=1`) — NEVER upstream `oraios/serena`.
- Treat Serena tool behavior (edit tools, memory tools, aliases) as changeable in our fork when weighing where to place a check or feature. Verify against `../em-serena/src/` before asserting what Serena can or cannot do.
- Deploy a Serena change: push `../em-serena` branch `swe`; the next `start-serena.sh` launch re-resolves the SHA.

## Runtime Files

`.serena/swe-setup-complete.json` (setup flag) · `.serena/swe-bypass.json` (legacy disable) · `.serena/swe-state/<session>.state` (authoritative state) · `.serena/streams/<session>.jsonl` (event log) · `.serena/streams/.init_<session>` (init sentinel) · `.serena/streams/.sweep_feature_<session>` (sweep sentinel, `mem:dom/DOM_SWE_FEATURE_GATES`) · `.serena/memories/WM_<session>.md` (per-session WM).

## Test Commands

`jq . state-machine/states.json` · `python3 scripts/validate-graph.py` · `claude plugin list | grep serena-workflow-engine`.

## Sweep Rule (canonical)

A docpending link surfaced by the PRIMARY feature is satisfied by read, planned (`(mem:<name>)` cited in WM Compliance Checklist), or ruled out (with reason); bare deferral is rejected. Mechanism: `mem:dom/DOM_SWE_FEATURE_GATES`.

## Hooks — Doc-Gate Fallback

`[doc-gate]` (`swe_pre_edit_validate.py`) falls back to extension-matched `dev/DEV_<LANG>` + `feature/FEATURE_DEV_STANDARDS` when a project's dev-standards memories carry no `paths:` front-matter for the edited file — `mem:dom/DOM_SWE_HOOKS_PRE_GATES_DOCS`. Give every `feature/*`/`dev/*` memory a `paths:` glob matching its governed files — precise `paths:` matching beats the extension fallback (the fallback cannot distinguish sibling languages sharing an extension, e.g. `.blade.php` vs plain `.php`).

## Related Memories

`ARCH_SWE` (architecture docs) · `REF_SWE_DEVELOPMENT` (dev standards) · `ref/REF_DEV_STANDARDS_ONBOARD` (parallel-agent discovery for an EXISTING codebase's dev standards, vs `swe-scaffold-project` which templates `FEATURE_DEV_STANDARDS` for a new empty project).

## Routing — When to Read a Child

| When                                         | Read                                   |
| -------------------------------------------- | -------------------------------------- |
| Hook mechanics (hub for HOOKS_* children)    | `mem:dom/DOM_SWE_HOOKS`                |
| State transitions, `states.json`, `loopCaps` | `mem:dom/DOM_SWE_STATE_MACHINE`        |
| Sweep gate, sentinels, docpending logic      | `mem:dom/DOM_SWE_FEATURE_GATES`        |
| Stop gate, config keys, detail triggers      | `mem:dom/DOM_SWE_RESPONSE_FORMAT_GATE` |
| New-project bootstrap, `/swe-bypass`         | `mem:dom/DOM_SWE_BOOTSTRAP`            |
| `memory-paths.conf`, memory aliasing         | `mem:dom/DOM_SWE_MEMORY_PATHS`         |
