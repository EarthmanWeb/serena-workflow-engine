---
name: FEATURE_SWE
description: Serena Workflow Engine plugin — source layout, state machine, hooks, MCP tools, feature gates, bootstrap/init flow, and dual-location edit rules.
metadata:
  type: feature
---

# FEATURE_SWE — Serena Workflow Engine

## Source Location (edit rules)

- This repo IS the plugin source. `hooks/`, `memories/`, `skills/`, `commands/`, `state-machine/`, `scripts/`, `agents/` sit directly under the working-directory root. Edit here.
- Target the repo root for ALL Serena/Glob/Grep searches of plugin source. NEVER target `.claude/plugins/...`.
- NEVER write to `.claude/plugins/serena-workflow-engine/` — it is the installed cache copy. See `FEEDBACK_PLUGIN_SOURCE_LOCATION`.
- Type: plugin. Languages: Python/Bash/JSON/Markdown. Framework: Claude Code Plugins.

## Architecture Layers

| Layer         | Purpose                        | Directory                               | Pattern               |
| ------------- | ------------------------------ | --------------------------------------- | --------------------- |
| State Machine | Workflow FSM (states in states.json) | `state-machine/`                  | FSM with transitions  |
| Core Modules  | Shared Python utilities        | `hooks/swe_hooks/core/`                 | Modular imports       |
| MCP Server    | WM update tools (swe-wm)       | `hooks/swe_hooks/mcp/`                  | Stdio JSON-RPC 2.0   |
| Hooks         | Event handlers for Claude Code | `hooks/{session,prompt,pre,post,stop}/` | Python scripts        |
| Skills        | User-invocable workflows       | `skills/`                               | YAML frontmatter + MD |
| Commands      | CLI shortcuts                  | `commands/`                             | Markdown              |
| Memories      | Workflow documentation         | `memories/`                             | Organized subdirs     |
| Agents        | Subagent definitions           | `agents/`                               | Markdown              |
| Scripts       | Build/deployment tools         | `scripts/`                              | Shell scripts         |

### Data Flow

`User Request → Hook (SessionStart) → WF_INIT → WF_CLASSIFY → State Machine → Hooks (Pre/Post) → Memory Persistence`

### State Machine Flow

```
SessionStart → WF_INITIAL_SETUP (first time) OR WF_INIT
WF_INIT → WF_CLASSIFY → WF_ARCH_REVIEW → WF_EXECUTE
         → WF_EXECUTE ↔ WF_CHECKPOINT → WF_VERIFY → WF_DONE → WF_CLEANUP
```

## Entry Points

- Main: `state-machine/states.json`
- Config: `.claude-plugin/plugin.json`
- Hooks config: `hooks/hooks.json`
- Init command: `commands/swe-init.md`

## Root Plugin Files

| File         | Purpose                  |
| ------------ | ------------------------ |
| `README.md`  | Plugin documentation     |
| `.mcp.json`  | MCP server configuration |
| `.gitignore` | Git ignore patterns      |

## States (12 in states.json)

| Category   | States                                                   |
| ---------- | -------------------------------------------------------- |
| Setup      | WF_INITIAL_SETUP, WF_ONBOARD                             |
| Entry      | WF_CLASSIFY, WF_CONTINUE                                 |
| Analysis   | WF_RESEARCH, WF_RESEARCH_LITE                            |
| Planning   | WF_ARCH_REVIEW                                           |
| Gates      | WF_CLARIFY                                               |
| Execution  | WF_EXECUTE, WF_CHECKPOINT, WF_DEBUG_TDD                  |
| Completion | WF_VERIFY, WF_DONE                                       |

## Core Modules (`hooks/swe_hooks/core/`)

| Module                | Purpose                                    |
| --------------------- | ------------------------------------------ |
| `state_manager.py`    | Workflow state transitions and persistence |
| `config.py`           | Configuration, paths, WM state read/write  |
| `session.py`          | Session ID and Working Memory management   |
| `input.py`            | Hook input parsing utilities               |
| `output.py`           | Hook output formatting                     |
| `stream.py`           | Append-only JSONL event log for sessions   |
| `wm_validator.py`     | Working Memory validation                  |

## MCP Server: swe-wm (`hooks/swe_hooks/mcp/`)

- Stdlib-only stdio MCP server exposing Working Memory update tools.
- Registered in `plugin.json` as `swe-wm`. Started via `scripts/start-wm-mcp.sh`.

| Tool                    | Purpose                                              |
| ----------------------- | ---------------------------------------------------- |
| `swe_wm_read`           | Read WM state + full content for a session           |
| `swe_wm_update`         | CANONICAL — batched status + section updates in ONE call; returns post-update state |
| `swe_wm_update_section` | Legacy single-section update (protects daemon fields) |
| `swe_wm_update_status`  | Legacy status-only update of `**[STATUS]**:` tag     |

- Protected sections (tools REJECT writes): `Workflow Context`, `Transitions`.
- Agent-owned sections: `Current Task`, `Progress`, `Files`, `Notes`, `Requirements`, `Implementation Notes`, `Previous Task`, `Task Context`, `Affected Features`, `Context`, `Feature(s)`.
- Usage: `mcp__swe-wm__swe_wm_update(session_id="...", status="IN_PROGRESS", sections=[{"section": "Progress", "content": "..."}, ...])` — one call per workflow step.

## Hooks (18 Python scripts by event type)

### Session Hooks (`hooks/session/`)

| Hook                   | Trigger      | Purpose                              |
| ---------------------- | ------------ | ------------------------------------ |
| `swe_session_start.py` | SessionStart | Initialize workflow state, create WM |
| `swe_session_end.py`   | SessionEnd   | Clean up sentinels, mark WM abandoned |

### User Prompt Hooks (`hooks/prompt/`)

| Hook                          | Trigger          | Purpose                         |
| ----------------------------- | ---------------- | ------------------------------- |
| `swe_user_prompt_workflow.py` | UserPromptSubmit | Intent analysis, state transitions, sentinel recovery |

### Pre-Tool Hooks (`hooks/pre/`)

| Hook                            | Trigger                        | Purpose                            |
| ------------------------------- | ------------------------------ | ---------------------------------- |
| `swe_pre_tool_init_gate.py`     | PreToolUse                     | Block ALL tools until WF_INIT read |
| `swe_pre_edit_validate.py`      | PreToolUse (Edit/Write/Serena) | Validate edit permissions          |
| `swe_pre_memory_index_gate.py`  | PreToolUse (Edit/Write/write_memory/edit_memory) | HARD-DENY spec/report/research/project links entering MEMORY.md |
| `swe_pre_bash_test_gate.py`     | PreToolUse (Bash)              | Feature gate: FEATURE_TESTS        |
| `swe_pre_search_docs_gate.py`   | PreToolUse (Grep/Glob/search_for_pattern/Bash-inspection; Read matched but never gated) | DOCS-FIRST gate, budget model: one FRESH docs consult clears the next 5 gated calls (re-reads don't refill); deny lists pending related docs; refill ≠ research |
| `swe_pre_question_consent_gate.py` | PreToolUse (AskUserQuestion) | Deny questions under blanket consent (`auto_approve`/`blanket_consent`) |

### Post-Tool Hooks (`hooks/post/`)

| Hook                                  | Trigger                         | Purpose                          |
| ------------------------------------- | ------------------------------- | -------------------------------- |
| `swe_post_read_state.py`              | PostToolUse (read_memory/list_memories/search_memories_by_*) | State transitions, plan mode; appends named `docread` (resets search streak, refills docs-gate budget, feeds sweep verification); searches surfacing unread docs get NO credit until read; reads surfacing unread mem:/[[…]] links append docpending + read-these instruction |
| `swe_post_edit_checkpoint.py`         | PostToolUse (Edit/Write/Serena) | Track edits, checkpoint at 10 edits |
| `swe_post_search_docs_hint.py`        | PostToolUse (Grep/Glob/search_for_pattern) | Docs-first sentinel: 3 consecutive wide searches → check memories first |
| `swe_post_todo_wm_sync.py`            | PostToolUse (TodoWrite)         | WM sync reminder on todo changes |
| `swe_post_write_continue.py`          | PostToolUse (Write)             | Post-write continuation          |
| `swe_post_memory_index.py`            | PostToolUse (write_memory)      | Enforce MEMORY.md index update   |
| `swe_post_memory_style.py`            | PostToolUse (write_memory/edit_memory) | Enforce terse-imperative memory style |
| `swe_post_tool_failure.py`            | PostToolUseFailure              | Flailing detection, failure logging |

### Stop Hooks (`hooks/stop/`)

| Hook                              | Trigger | Purpose                                   |
| --------------------------------- | ------- | ----------------------------------------- |
| `swe_stop_continue_working.py`    | Stop    | Block unnecessary stops, continue-working |

## Skills (14 total)

| Skill                      | Purpose                                             |
| -------------------------- | --------------------------------------------------- |
| `swe-feature-onboard`      | Onboard new feature to workflow                     |
| `swe-feature-update`       | Update feature memory files                         |
| `swe-gherkin-spec`         | Author Gherkin BDD specs                            |
| `swe-gherkin-dev`          | TDD implementation from Gherkin specs               |
| `swe-memory-audit`         | Audit memories against the terse-imperative style   |
| `swe-memory-frontmatter`   | Audit/backfill memory YAML front-matter             |
| `swe-scaffold-project`     | Initialize new project                              |
| `swe-symbol-index`         | Generate symbol index table for feature linked docs |
| `swe-wm-update`            | Update Working Memory sections                      |
| `swe-workflow-research`    | Code exploration/research                           |
| `swe-workflow-arch-review` | Architecture compliance review                      |
| `swe-workflow-debug-tdd`   | Test-driven debugging                               |
| `swe-workflow-verify`      | Verify implementation                               |
| `swe-wp-cli-setup`         | Configure the WP-CLI MCP server                     |

## Commands (9 total)

| Command                  | Purpose                    |
| ------------------------ | -------------------------- |
| `/swe-init`              | Initialize SWE for project |
| `/swe-status`            | Show workflow state        |
| `/swe-reset`             | Reset workflow state       |
| `/swe-goto`              | Force transition to state  |
| `/swe-bypass`            | Disable SWE for project — USER-ONLY (`disable-model-invocation: true`) |
| `/swe-cleanup`           | Archive completed memories |
| `/swe-symlink-memory`    | Set up auto-memory symlink |
| `/swe-memory-frontmatter`| Audit/backfill memory front-matter |
| `/swe-wp-cli-setup`      | Configure the WP-CLI MCP server |

### CLI Tools (non-skill)

| Command | Purpose |
| ------- | ------- |
| `python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel [session_id]` | Manual sentinel reset for deadlock recovery |

## Agents (1 total)

| Agent            | Purpose                   |
| ---------------- | ------------------------- |
| `swe-init-agent` | Autonomous initialization |

## Memories Organization

| Directory           | Contents                                                     |
| ------------------- | ------------------------------------------------------------ |
| `memories/wf/`      | Workflow state instructions (WF_*.md)                        |
| `memories/ref/`     | Reference docs (FEATURE_DEV_STANDARDS, REF_MEMORY_STYLE, etc.) |
| `memories/claude/`  | Claude behavior docs (CLAUDE.md, CLAUDE_OBLIGATIONS.md)      |
| `memories/arch/`    | Architecture documentation (ARCH_SWE.md)                     |
| `memories/dom/`     | Domain documentation (DOM_SWE_HOOKS.md)                      |
| `memories/feature/` | Feature configs (FEATURE_SWE.md)                             |
| `memories/index/`   | Index files (if any)                                         |

## Feature Gate Pattern

Feature gates block specific tools until the relevant FEATURE_* memory is read. All feature gates use session-scoped sentinel files for O(1) checks.

### Mechanism

1. Pre-tool hook checks for sentinel file `.serena/streams/.{gate}_feature_{session_id}`.
2. If missing → block with instruction to read the FEATURE_* memory.
3. Post-read hook (`swe_post_read_state.py`) creates the sentinel via `create_feature_sentinel(session_id, gate_name)`.
4. Subsequent tool calls pass instantly (file-existence check).

### Registered Gates

| Gate Name | Pre-Hook                        | Blocks                 | Sentinel                   | Feature Memory |
| --------- | ------------------------------- | ---------------------- | -------------------------- | -------------- |
| `test`    | `swe_pre_bash_test_gate.py`     | `npx playwright test`  | `.test_feature_{session}`  | FEATURE_TESTS  |
| `sweep`   | `swe_pre_edit_validate.py`      | ALL edits in execution states | `.sweep_feature_{session}` | (WM-verified, not read-created — see below) |

### The `sweep` Gate (per-task, WM-verified)

Unlike read-created feature gates, the sweep sentinel is created ONLY by the WM server: an `Affected Features` write whose `**Memories loaded**:` list is verified against the task's actual named `docread` events (`_check_memory_sweep` in `wm_server.py`). Every transition INTO WF_CLASSIFY deletes it (`clear_sweep_sentinel` in `state_manager.py`), so same-session follow-up tasks must re-sweep before their first edit. Contract: `wf/WF_CLASSIFY` Steps 4d/4e. Tests: `tests/test_sweep_gate.py`.

### Adding a New Gate

1. Create pre-hook `hooks/pre/swe_pre_{name}_gate.py` — check sentinel, block if missing.
2. In `swe_post_read_state.py`, call `create_feature_sentinel(session_id, '{gate_name}')` when FEATURE_* is read.
3. Register in `hooks/hooks.json`.
4. Add a directive to the FEATURE_* memory documenting the gate.

## Plan Mode Triggers

| Mode        | States                                                                   |
| ----------- | ------------------------------------------------------------------------ |
| Always      | WF_ARCH_REVIEW                                                           |
| Never       | WF_DEBUG_TDD, WF_CHECKPOINT, WF_VERIFY, WF_DONE, WF_RESEARCH, WF_EXECUTE |
| Conditional | WF_CLASSIFY (complexity >= medium)                                       |

## RLVR Learning

| Signal Type         | States         | Impact                    |
| ------------------- | -------------- | ------------------------- |
| trajectory_init     | WF_CLASSIFY    | baseline                  |
| routing_decision    | WF_CLASSIFY    | neutral                   |
| clarify_visit       | WF_CLARIFY     | penalty (-0.1)            |
| arch_review         | WF_ARCH_REVIEW | bonus (+0.1)              |
| verify_check        | WF_VERIFY      | bonus if first try (+0.1) |
| learning_checkpoint | WF_DONE        | mandatory                 |

## Scripts

| Script                | Purpose                                    |
| --------------------- | ------------------------------------------ |
| `bump-version.sh`     | Version management                         |
| `install-hooks.sh`    | Install git hooks                          |
| `pre-commit`          | Pre-commit validation                      |
| `swe-bootstrap.py`    | Self-contained new project bootstrap       |
| `start-serena.sh`     | Start Serena LSP server                    |
| `start-wm-mcp.sh`     | Start WM MCP server                        |
| `serena_memory_patch.py` | Serena memory path patching             |

## Dependencies

- Internal: Serena MCP (memory), swe-wm MCP (Working Memory updates).
- External: jq (JSON parsing), bash, python3.

## Runtime Files

| File                               | Purpose                            |
| ---------------------------------- | ---------------------------------- |
| `.serena/swe-setup-complete.json`  | Setup completion flag              |
| `.serena/swe-bypass.json`          | SWE permanently disabled flag      |
| `.serena/swe-state/<session>.state`| Decoupled workflow state (authoritative) |
| `.serena/streams/<session>.jsonl`  | Append-only event log              |
| `.serena/streams/.init_<session>`  | Init gate sentinel cache (self-healing: recreated from WM if missing) |
| `.serena/streams/.sweep_feature_<session>` | Per-task Feature Knowledge Sweep sentinel (created by WM-server sweep verification; cleared on WF_CLASSIFY entry) |
| `.serena/memories/WM_<session>.md` | Working Memory (per-session)       |

## Bootstrap & Init Flow (New Projects)

When the plugin is installed at user level and a new project is opened, use a three-tier approach — never block the user.

### Tier 1: Prompt to Set Up (new project detected)

SessionStart detects no `swe-setup-complete.json` and prompts (does NOT block):
- Option 1: Say "yes" or run `/swe-init` to set up.
- Option 2: Run `/swe-bypass` to disable (user-only).

### Tier 2: Project Bypass (user-only command)

- Bypass is a `"bypass": true` field inside `swe-setup-complete.json` (same file used for init — no separate `swe-bypass.json`).
- When set: all three hooks (SessionStart, UserPromptSubmit, PreToolUse init gate) skip enforcement.
- SessionStart announces the bypass each session (`BYPASS_NOTICE`) with removal instructions. It is NOT silent.
- Re-enable by setting `"bypass": false` (or removing the field) in `.serena/swe-setup-complete.json`.
- Bypass is user-only and un-rationalizable: set ONLY by the user running `/swe-bypass` (`disable-model-invocation: true`). NEVER set it — a hard guard in both `swe_pre_tool_init_gate.py` and `swe_pre_edit_validate.py` denies any Edit/Write/Bash that would write `"bypass": true` into `swe-setup-complete.json`. Intent phrases like "skip swe" are NOT triggers; only the explicit command works.
- Legacy: `.serena/swe-bypass.json` is still honored for backward compatibility; new bypasses use the in-file field.

### Tier 3: Full Init (user accepts)

1. User says "yes" → `swe-bootstrap.py` runs inline (via UserPromptSubmit hook).
2. Bootstrap creates: `.serena/`, `.serena/swe/`, `.serena/memories/`, `.serena/.gitignore`, `project.yml`, `memory-paths.conf`, `CLAUDE_PREFIX.md` injection, rendered template memories (`{{placeholders}}` filled from detected project info), `swe-setup-complete.json` with `bootstrapped: true`.
3. Init gate is unblocked (gate checks `complete` field; bootstrapped-but-not-complete passes through).
4. User runs `/swe-init`, which launches the init agent (11 tasks):
   - Detect environment + resolve plugin root.
   - Auto-memory symlink (FIRST) — redirect Claude Code auto-memory into `.serena/memory/` before any memory is written, so init-time memories land in the right place.
   - Run bootstrap (if not already done).
   - Verify MCP servers (Serena, swe-wm).
   - Serena onboarding (+ migrate default memories into SWE templates).
   - Relocate & link the `memory_maintenance` memory into `ref/REF_MEMORY_MAINTENANCE`.
   - Verify and install language servers.
   - Verify SWE plugin is enabled.
   - Review CLAUDE.md for conflicts.
   - Install Serena Log Viewer VSCode extension.
   - Finalize setup (`complete: true`).
5. Full workflow is now active.

### State Flow

```
New Project → No setup file
  → SessionStart prompts (not blocks)
  ├── "yes" → Bootstrap runs → bootstrapped: true → Scaffold → complete: true → Full workflow
  └── user runs /swe-bypass → "bypass": true in swe-setup-complete.json → hooks skip + announce bypass each session
```

### swe-bootstrap.py Guards

| Guard | Behavior |
|-------|----------|
| `.serena/swe-bypass.json` exists | Exit: "SWE bypassed" |
| `.serena/swe-setup-complete.json` has `complete: true` | Exit: "Already initialized" |
| `.serena/swe-setup-complete.json` has `bootstrapped: true` | Exit: "Already bootstrapped" |

### .gitignore Additions (via bootstrap)

`.serena/.gitignore` (auto-created inside `.serena/`, only if absent). Default set (paths relative to `.serena/`):
```
/cache
/streams
/memories
/swe-setup-complete
```
`/memories` blanket-ignores the plural session-WM dir (`.serena/memories/`, holds `WM_*.md`). Committed typed feature memories live in the singular `.serena/memory/` and are NOT matched. Source: `ensure_serena_gitignore()` in `scripts/swe-bootstrap.py`.

Project root `.gitignore` (appended by `update_gitignore()`, guarded by the `!.serena/memory/` marker):
```
.serena/swe-bypass.json
.serena/swe-setup-complete.json
.serena/swe-state/

# Override global .serena/* ignore — un-ignore project memories
!.serena/memory/
!.serena/memory/**/*.md
!.serena/memories/
!.serena/memories/**/*.md
.serena/memories/WM_*.md
```

## Test Commands

```bash
# Validate state machine
jq . .claude/plugins/serena-workflow-engine/state-machine/states.json

# Check hook permissions
ls -la .claude/plugins/serena-workflow-engine/hooks/**/*.py

# Verify plugin installation
claude plugin list | grep serena-workflow-engine
```

## Development Standards (Dual-Location Architecture)

SWE is a standalone plugin with a dual-location architecture.

### Location 1: Plugin Folder (generic/portable)

Path: `.claude/plugins/serena-workflow-engine/`. Contains files that must work across ANY project using the plugin:
- `memories/wf/WF_*.md` — Workflow state instructions
- `memories/ref/REF_*.md` — Generic reference docs
- `hooks/{session,prompt,pre,post,stop}/*.py` — Event handler scripts
- `hooks/swe_hooks/core/*.py` — Core Python modules
- `hooks/hooks.json` — Hook configuration (auto-loaded by plugin system)
- `skills/*/SKILL.md` — Skill definitions
- `commands/*.md` — Command definitions
- `agents/*.md` — Agent definitions
- `scripts/*.sh` — Build scripts
- `README.md` — Plugin documentation

### Location 2: Local Serena Memories (project-specific)

Path: `.serena/swe/` — feature memories, refs, specs:
- `wf/WF_*.md` — Copied from plugin, may have project customizations
- `ref/REF_*.md` — Project-specific references
- `dom/DOM_SWE_*.md` — Domain documentation
- `feature/FEATURE_SWE.md` — This file

Path: `.serena/memories/` — session Working Memory:
- `WM_<session>.md` — Per-session working memory files

### Change Decision Matrix

| Change Type               | Plugin Folder | Local Memories | Example             |
| ------------------------- | ------------- | -------------- | ------------------- |
| Generic workflow logic    | ✅ YES        | ❌ No          | New WF_* state      |
| Generic hook behavior     | ✅ YES        | ❌ No          | Hook pattern change |
| Project-specific patterns | ❌ No         | ✅ YES         | Custom DOM_* doc    |
| New skill/command         | ✅ YES        | ❌ No          | New /swe-* command  |
| Reference documentation   | ✅ YES        | ❌ No          | REF_* updates       |
| Hook script changes       | ✅ YES        | ❌ No          | Python hook edits   |

### Hook Loading

- SWE hooks load automatically from the plugin folder via Claude Code's plugin system.
- `${CLAUDE_PLUGIN_ROOT}` in `hooks/hooks.json` resolves automatically — no copying to settings.json needed.
- See `DOM_SWE_HOOKS` for hook architecture details.

## Related Memories

- `ARCH_SWE` — SWE architecture documentation
- `REF_SWE_DEVELOPMENT` — Development standards
- `DOM_SWE_HOOKS` — Hook architecture
