# FEATURE_SWE - Serena Workflow Engine

## Overview

- **Name:** Serena Workflow Engine
- **Type:** plugin
- **Language:** Python/Bash/JSON/Markdown
- **Framework:** Claude Code Plugins
- **Root Path:** `.claude/plugins/serena-workflow-engine`
- **Last Updated:** 2026-05-06

## Architecture

### Layers

| Layer         | Purpose                        | Directory                               | Pattern               |
| ------------- | ------------------------------ | --------------------------------------- | --------------------- |
| State Machine | Workflow FSM (states in states.json) | `state-machine/`                  | FSM with transitions  |
| Core Modules  | Shared Python utilities        | `hooks/swe_hooks/core/`                 | Modular imports       |
| MCP Server    | WM update tools (swe-wm)       | `hooks/swe_hooks/mcp/`                  | Stdio JSON-RPC 2.0   |
| Hooks         | Event handlers for Claude Code | `hooks/{session,prompt,pre,post,stop}/` | Python scripts        |
| Skills        | User-invocable workflows       | `skills/`                               | YAML frontmatter + MD |
| Commands      | CLI shortcuts                  | `commands/`                             | Markdown              |
| Memories      | Workflow documentation         | `memories/`                             | Organized subdirs     |
| Agents        | Swarm agent definitions        | `agents/`                               | Markdown              |
| Scripts       | Build/deployment tools         | `scripts/`                              | Shell scripts         |

### Data Flow

`User Request → Hook (SessionStart) → WF_INIT → WF_CLASSIFY → State Machine → Hooks (Pre/Post) → Memory Persistence`

### State Machine Flow

```
SessionStart → WF_INITIAL_SETUP (first time) OR WF_INIT
WF_INIT → WF_CLASSIFY → WF_ARCH_REVIEW → WF_EXECUTE
                                        → WF_SWARM_ORCHESTRATE → WF_EXECUTE
         → WF_EXECUTE ↔ WF_CHECKPOINT → WF_VERIFY → WF_DONE → WF_CLEANUP
```

## Entry Points

- **Main:** `state-machine/states.json`
- **Config:** `.claude-plugin/plugin.json`
- **Hooks Config:** `hooks/hooks.json`
- **Init Command:** `commands/swe-init.md`

## Root Plugin Files

| File         | Purpose                  |
| ------------ | ------------------------ |
| `README.md`  | Plugin documentation     |
| `.mcp.json`  | MCP server configuration |
| `.gitignore` | Git ignore patterns      |

## Core Components

### States (14 in states.json)

| Category   | States                                                   |
| ---------- | -------------------------------------------------------- |
| Setup      | WF_INITIAL_SETUP, WF_ONBOARD                             |
| Entry      | WF_CLASSIFY, WF_CONTINUE                                 |
| Analysis   | WF_RESEARCH, WF_RESEARCH_LITE                            |
| Planning   | WF_ARCH_REVIEW, WF_SWARM_ORCHESTRATE                     |
| Gates      | WF_CLARIFY                                               |
| Execution  | WF_EXECUTE, WF_CHECKPOINT, WF_DEBUG_TDD |
| Completion | WF_VERIFY, WF_DONE                                       |

### Core Modules (swe_hooks/core/)

| Module                | Purpose                                    |
| --------------------- | ------------------------------------------ |
| `state_manager.py`    | Workflow state transitions and persistence |
| `config.py`           | Configuration, paths, WM state read/write  |
| `session.py`          | Session ID and Working Memory management   |
| `input.py`            | Hook input parsing utilities               |
| `output.py`           | Hook output formatting                     |
| `stream.py`           | Append-only JSONL event log for sessions   |
| `wm_validator.py`     | Working Memory validation                  |

### MCP Server: swe-wm (`hooks/swe_hooks/mcp/`)

Lightweight stdio MCP server exposing Working Memory update tools. Stdlib only.
Registered in `plugin.json` as `swe-wm`, started via `scripts/start-wm-mcp.sh`.

| Tool                    | Purpose                                              |
| ----------------------- | ---------------------------------------------------- |
| `swe_wm_read`           | Read WM state + full content for a session           |
| `swe_wm_update_section` | Update agent-owned section (protects daemon fields)  |
| `swe_wm_update_status`  | Update `**[STATUS]**:` tag in Current Task           |

**Protected sections** (rejected by tools): `Workflow Context`, `Transitions`

**Agent-owned sections**: `Current Task`, `Progress`, `Files`, `Notes`,
`Requirements`, `Implementation Notes`, `Previous Task`, `Task Context`,
`Affected Features`, `Context`, `Feature(s)`

**Usage**: `mcp__swe-wm__swe_wm_update_section(session_id="...", section="Progress", content="...")`

### Hooks (15 Python scripts organized by event type)

#### Session Hooks (`hooks/session/`)

| Hook                   | Trigger      | Purpose                              |
| ---------------------- | ------------ | ------------------------------------ |
| `swe_session_start.py` | SessionStart | Initialize workflow state, create WM |
| `swe_session_end.py`   | SessionEnd   | Clean up sentinels, mark WM abandoned |

#### User Prompt Hooks (`hooks/prompt/`)

| Hook                          | Trigger          | Purpose                         |
| ----------------------------- | ---------------- | ------------------------------- |
| `swe_user_prompt_workflow.py` | UserPromptSubmit | Intent analysis, state transitions, sentinel recovery |
| `swe_user_prompt_swarm.py`    | UserPromptSubmit | Detect swarm keywords           |

#### Pre-Tool Hooks (`hooks/pre/`)

| Hook                            | Trigger                        | Purpose                            |
| ------------------------------- | ------------------------------ | ---------------------------------- |
| `swe_pre_tool_init_gate.py`     | PreToolUse                     | Block ALL tools until WF_INIT read |
| `swe_pre_edit_validate.py`      | PreToolUse (Edit/Write/Serena) | Validate edit permissions          |
| `swe_pre_bash_test_gate.py`     | PreToolUse (Bash)              | Feature gate: FEATURE_TESTS        |
| `swe_pre_swarm_feature_gate.py` | PreToolUse (ruflo swarm)       | Feature gate: FEATURE_SWARM        |

#### Post-Tool Hooks (`hooks/post/`)

| Hook                                  | Trigger                         | Purpose                          |
| ------------------------------------- | ------------------------------- | -------------------------------- |
| `swe_post_read_state.py`              | PostToolUse (read_memory)       | State transitions, plan mode     |
| `swe_post_edit_checkpoint.py`         | PostToolUse (Edit/Write/Serena) | Track edits, checkpoint at 10 edits |
| `swe_post_todo_wm_sync.py`            | PostToolUse (TodoWrite)         | WM sync reminder on todo changes |
| `swe_post_write_continue.py`          | PostToolUse (Write)             | Post-write continuation          |
| `swe_post_memory_index.py`            | PostToolUse (write_memory)      | Enforce MEMORY.md index update   |
| `swe_post_tool_failure.py`            | PostToolUseFailure              | Flailing detection, failure logging |

#### Stop Hooks (`hooks/stop/`)

| Hook                              | Trigger | Purpose                                   |
| --------------------------------- | ------- | ----------------------------------------- |
| `swe_stop_continue_working.py`    | Stop    | Block unnecessary stops, continue-working |

### Skills (10 total)

| Skill                      | Purpose                                             |
| -------------------------- | --------------------------------------------------- |
| `swe-feature-onboard`      | Onboard new feature to workflow                     |
| `swe-feature-update`       | Update feature memory files                         |
| `swe-scaffold-project`     | Initialize new project                              |
| `swe-symbol-index`         | Generate symbol index table for feature linked docs |
| `swe-wm-update`            | Update Working Memory sections                      |
| `swe-swarm-orchestrate`    | Multi-agent swarm coordination                      |
| `swe-swarm-analyze`        | DAA-powered codebase analysis                       |
| `swe-workflow-debug-tdd`   | Test-driven debugging                               |
| `swe-workflow-verify`      | Verify implementation                               |
| `swe-workflow-research`    | Code exploration/research                           |
| `swe-workflow-arch-review` | Architecture compliance review                      |

### Commands (7 total)

| Command         | Purpose                    |
| --------------- | -------------------------- |
| `/swe-init`     | Initialize SWE for project |
| `/swe-status`   | Show workflow state        |
| `/swe-reset`    | Reset workflow state       |
| `/swe-goto`     | Force transition to state  |
| `/swe-bypass`   | Disable SWE for project — USER-ONLY (`disable-model-invocation: true`) |
| `/swe-memory`   | Manage session WM          |
| `/swe-scaffold-project` | Scaffold new project (skill) |
| `/swe-cleanup`  | Archive completed memories |

**CLI Tools (non-skill):**

| Command | Purpose |
| ------- | ------- |
| `python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel [session_id]` | Manual sentinel reset for deadlock recovery |

### Agents (1 total)

| Agent                      | Purpose                   |
| -------------------------- | ------------------------- |
| `swe-init-agent`           | Autonomous initialization |

## Memories Organization

Memories are organized in subdirectories:

| Directory           | Contents                                                     |
| ------------------- | ------------------------------------------------------------ |
| `memories/wf/`      | Workflow state instructions (WF_*.md)                        |
| `memories/ref/`     | Reference docs (FEATURE_DEV_STANDARDS, REF_SWARM_PATTERNS, etc.) |
| `memories/claude/`  | Claude behavior docs (CLAUDE.md, CLAUDE_OBLIGATIONS.md)      |
| `memories/arch/`    | Architecture documentation (ARCH_SWE.md)                     |
| `memories/dom/`     | Domain documentation (DOM_SWE_HOOKS.md)                      |
| `memories/feature/` | Feature configs (FEATURE_SWE.md)                             |
| `memories/index/`   | Index files (if any)                                         |

## Feature Gate Pattern

Feature gates block specific tools until the relevant FEATURE_* memory has been
read. All feature gates use **session-scoped sentinel files** for O(1) checks.

### How It Works

1. **Pre-tool hook** checks for sentinel file:
   `.serena/streams/.{gate}_feature_{session_id}`
2. If missing → **block** with instruction to read FEATURE_* memory
3. **Post-read hook** (`swe_post_read_state.py`) creates sentinel via
   `create_feature_sentinel(session_id, gate_name)`
4. Subsequent tool calls pass instantly (file existence check)

### Registered Gates

| Gate Name | Pre-Hook                        | Blocks                 | Sentinel                   | Feature Memory |
| --------- | ------------------------------- | ---------------------- | -------------------------- | -------------- |
| `test`    | `swe_pre_bash_test_gate.py`     | `npx playwright test`  | `.test_feature_{session}`  | FEATURE_TESTS  |
| `swarm`   | `swe_pre_swarm_feature_gate.py` | `ruflo swarm_init`     | `.swarm_feature_{session}` | FEATURE_SWARM  |

### Adding a New Gate

1. Create pre-hook: `hooks/pre/swe_pre_{name}_gate.py` — check sentinel, block
   if missing
2. Add to `swe_post_read_state.py`: call
   `create_feature_sentinel(session_id, '{gate_name}')` when FEATURE_* is read
3. Register in `hooks/hooks.json`
4. Add directive to FEATURE_* memory documenting the gate

## Plan Mode Triggers

| Mode        | States                                                                   |
| ----------- | ------------------------------------------------------------------------ |
| Always      | WF_ARCH_REVIEW, WF_SWARM_ORCHESTRATE                                     |
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

- **Internal:** Serena MCP (memory), swe-wm MCP (Working Memory updates)
- **External:** jq (JSON parsing), bash, python3

## Runtime Files

| File                               | Purpose                            |
| ---------------------------------- | ---------------------------------- |
| `.serena/swe-setup-complete.json`  | Setup completion flag              |
| `.serena/swe-bypass.json`          | SWE permanently disabled flag      |
| `.serena/swe-state/<session>.state`| Decoupled workflow state (authoritative) |
| `.serena/streams/<session>.jsonl`  | Append-only event log              |
| `.serena/streams/.init_<session>`  | Init gate sentinel cache (self-healing: recreated from WM if missing) |
| `.serena/memories/WM_<session>.md` | Working Memory (per-session)       |

## Bootstrap & Init Flow (New Projects)

When the SWE plugin is installed at user level and a new project is opened, the plugin
uses a three-tier approach to avoid blocking the user:

### Tier 1: Prompt to Set Up (new project detected)

SessionStart detects no `swe-setup-complete.json` and **prompts** (not blocks):
- Option 1: Say "yes" or run `/swe-init` to set up
- Option 2: Run the `/swe-bypass` command to disable (user-only)

### Tier 2: Project Bypass (user-only command)

The bypass is a `"bypass": true` field **inside `swe-setup-complete.json`** (the
same file used for init — no separate `swe-bypass.json`). When set:
- All three hooks (SessionStart, UserPromptSubmit, PreToolUse init gate) skip enforcement
- SessionStart **announces** the bypass each session (`BYPASS_NOTICE`) with removal instructions — it is NOT silent
- Re-enable by setting `"bypass": false` (or removing the field) in `.serena/swe-setup-complete.json`

**Bypass is user-only and un-rationalizable.** It is set ONLY by the user running
the `/swe-bypass` command (`disable-model-invocation: true`). The assistant must
never set it — and cannot: a hard guard in both `swe_pre_tool_init_gate.py` and
`swe_pre_edit_validate.py` denies any Edit/Write/Bash that would write
`"bypass": true` into `swe-setup-complete.json`. Intent phrases like "skip swe"
are NOT triggers; only the explicit command works.

> Legacy: `.serena/swe-bypass.json` is still honored for backward compatibility,
> but new bypasses use the in-file field.

### Tier 3: Full Init (user accepts)

1. User says "yes" → `swe-bootstrap.py` runs inline (via UserPromptSubmit hook)
2. Bootstrap creates: `.serena/`, `.serena/swe/`, `.serena/memories/`, `.serena/.gitignore`, `project.yml`, `memory-paths.conf`, `CLAUDE_PREFIX.md` injection, rendered template memories (with `{{placeholders}}` filled from detected project info), `swe-setup-complete.json` with `bootstrapped: true`
3. Init gate is **unblocked** (gate checks `complete` field; bootstrapped-but-not-complete passes through)
4. User runs `/swe-init` which launches the init agent (9 tasks):
   - Detect environment + resolve plugin root
   - Run bootstrap (if not already done)
   - Verify MCP servers (Serena, swe-wm)
   - Serena onboarding
   - Verify and install language servers
   - Verify SWE plugin is enabled
   - Review CLAUDE.md for conflicts
   - Install Serena Log Viewer VSCode extension
   - Finalize setup (`complete: true`)
5. Full workflow is now active

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

**`.serena/.gitignore`** (auto-created inside `.serena/`):
```
streams/
memories/WM_*.md
memories/LITE_MODE_*.md
swe-state/
swe-bypass.json
swe-setup-complete.json
```

**Project root `.gitignore`** (appended):
```
.serena/swe-bypass.json
.serena/swe-setup-complete.json
.serena/swe-state/
!.serena/swe/
!.serena/swe/**/*.md
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

## ⚠️ Development Standards (Dual-Location Architecture)

SWE is a **standalone plugin** with a **dual-location architecture**:

### Location 1: Plugin Folder (Generic/Portable)

**Path:** `.claude/plugins/serena-workflow-engine/`

Contains files that should work across ANY project using the plugin:

- `memories/wf/WF_*.md` - Workflow state instructions
- `memories/ref/REF_*.md` - Generic reference docs
- `hooks/{session,prompt,pre,post,stop}/*.py` - Event handler scripts
- `hooks/swe_hooks/core/*.py` - Core Python modules
- `hooks/hooks.json` - Hook configuration (auto-loaded by plugin system)
- `skills/*/SKILL.md` - Skill definitions
- `commands/*.md` - Command definitions
- `agents/*.md` - Agent definitions
- `scripts/*.sh` - Build scripts
- `README.md` - Plugin documentation

### Location 2: Local Serena Memories (Project-Specific)

**Path:** `.serena/swe/` — feature memories, refs, specs

- `wf/WF_*.md` - Copied from plugin, may have project customizations
- `ref/REF_*.md` - Project-specific references
- `dom/DOM_SWE_*.md` - Domain documentation
- `feature/FEATURE_SWE.md` - This file

**Path:** `.serena/memories/` — session Working Memory

- `WM_<session>.md` - Per-session working memory files

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

**SWE hooks load automatically from the plugin folder** via Claude Code's plugin
system. The `${CLAUDE_PLUGIN_ROOT}` variable in `hooks/hooks.json` is resolved
automatically - no copying to settings.json needed.

See `DOM_SWE_HOOKS` for hook architecture details.

## Related Memories

- [ARCH_SWE](ARCH_SWE) - SWE architecture documentation
- [REF_SWE_DEVELOPMENT](REF_SWE_DEVELOPMENT) - Development standards
- [DOM_SWE_HOOKS](DOM_SWE_HOOKS) - Hook architecture
