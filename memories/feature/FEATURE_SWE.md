# FEATURE_SWE - Serena Workflow Engine

## Overview
- **Name:** Serena Workflow Engine
- **Type:** plugin
- **Language:** Python/Bash/JSON/Markdown
- **Framework:** Claude Code Plugins
- **Root Path:** `.claude/plugins/serena-workflow-engine`
- **Last Updated:** 2026-01-25

## Architecture

### Layers
| Layer | Purpose | Directory | Pattern |
|-------|---------|-----------|---------|
| State Machine | 21-state workflow engine | `state-machine/` | FSM with transitions |
| Core Modules | Shared Python utilities | `hooks/swe_hooks/core/` | Modular imports |
| Hooks | Event handlers for Claude Code | `hooks/{session,prompt,pre,post,stop}/` | Python scripts |
| Skills | User-invocable workflows | `skills/` | YAML frontmatter + MD |
| Commands | CLI shortcuts | `commands/` | Markdown |
| Memories | Workflow documentation | `memories/` | Organized subdirs |
| Agents | Swarm agent definitions | `agents/` | Markdown |
| Scripts | Build/deployment tools | `scripts/` | Shell scripts |

### Data Flow
`User Request → Hook (SessionStart) → WF_START → State Machine → Hooks (Pre/Post) → Memory Persistence`

### State Machine Flow
```
SessionStart → WF_INITIAL_SETUP (first time) OR WF_START
WF_START → WF_CLASSIFY → WF_DETECT_REQ/WF_PLAN_ARCHITECTURE/WF_SWARM_ORCHESTRATE
         → WF_LOAD_FEATURE → WF_ARCH_REVIEW → WF_ASK_PERMISSION
         → WF_EXECUTE ↔ WF_CHECKPOINT → WF_VERIFY → WF_DONE → WF_CLEANUP
```

## Entry Points
- **Main:** `state-machine/states.json`
- **Config:** `.claude-plugin/plugin.json`
- **Hooks Config:** `hooks/hooks.json`
- **Init Command:** `commands/swe-init.md`

## Root Plugin Files
| File | Purpose |
|------|---------|
| `README.md` | Plugin documentation |
| `.mcp.json` | MCP server configuration |
| `.gitignore` | Git ignore patterns |

## Core Components

### States (21 total)
| Category | States |
|----------|--------|
| Setup | WF_INITIAL_SETUP, WF_ONBOARD |
| Entry | WF_INIT, WF_START, WF_CLASSIFY, WF_CONTINUE |
| Analysis | WF_RESEARCH, WF_RESEARCH_LITE, WF_DETECT_REQ, WF_REQUIREMENT |
| Planning | WF_PLAN_ARCHITECTURE, WF_ARCH_REVIEW, WF_SWARM_ORCHESTRATE |
| Gates | WF_CLARIFY, WF_ASK_PERMISSION |
| Execution | WF_LOAD_FEATURE, WF_UPDATE_MEMORY, WF_EXECUTE, WF_CHECKPOINT, WF_DEBUG_TDD |
| Completion | WF_VERIFY, WF_DONE, WF_CLEANUP |

### Core Modules (swe_hooks/core/)
| Module | Purpose |
|--------|---------|
| `state_manager.py` | Workflow state transitions and persistence |
| `config.py` | Configuration loading and constants |
| `session.py` | Session ID and Working Memory management |
| `input.py` | Hook input parsing utilities |
| `output.py` | Hook output formatting |
| `wm_validator.py` | Working Memory validation |
| `wm_writer_daemon.py` | Async WM writing |

### Hooks (13 Python scripts organized by event type)

#### Session Hooks (`hooks/session/`)
| Hook | Trigger | Purpose |
|------|---------|---------|
| `swe_session_start.py` | SessionStart | Initialize workflow state, create WM |

#### User Prompt Hooks (`hooks/prompt/`)
| Hook | Trigger | Purpose |
|------|---------|---------|
| `swe_user_prompt_workflow.py` | UserPromptSubmit | WF_INIT gate, state transitions |
| `swe_user_prompt_swarm.py` | UserPromptSubmit | Detect swarm keywords |

#### Pre-Tool Hooks (`hooks/pre/`)
| Hook | Trigger | Purpose |
|------|---------|---------|
| `swe_pre_tool_init_gate.py` | PreToolUse | Block ALL tools until WF_INIT read |
| `swe_pre_edit_validate.py` | PreToolUse (Edit/Write/Serena) | Validate edit permissions |
| `swe_pre_bash_test_gate.py` | PreToolUse (Bash) | Validate test commands |

#### Post-Tool Hooks (`hooks/post/`)
| Hook | Trigger | Purpose |
|------|---------|---------|
| `swe_post_read_state.py` | PostToolUse (read_memory) | State transitions, plan mode |
| `swe_post_edit_checkpoint.py` | PostToolUse (Edit/Write/Serena) | Track edits, trigger checkpoints |
| `swe_post_serena_replace_fallback.py` | PostToolUse (Serena replace) | Symbol replace fallback handling |
| `swe_post_task_learn.py` | PostToolUse (read_memory) | RLVR learning |
| `swe_post_ruv_swarm_init.py` | PostToolUse (ruv_swarm) | RUV-Swarm initialization |

#### Stop Hooks (`hooks/stop/`)
| Hook | Trigger | Purpose |
|------|---------|---------|
| `swe_stop_workflow_check.py` | Stop | Verify WF_DONE reached |

### Skills (12 total)
| Skill | Purpose |
|-------|---------|
| `swe-feature-onboard` | Onboard new feature to workflow |
| `swe-feature-update` | Update feature memory files |
| `swe-scaffold-project` | Initialize new project |
| `swe-sync` | Sync plugin to local memories |
| `swe-wm-update` | Update Working Memory sections |
| `swe-swarm-orchestrate` | Multi-agent swarm coordination |
| `swe-swarm-analyze` | DAA-powered codebase analysis |
| `swe-workflow-debug-tdd` | Test-driven debugging |
| `swe-workflow-detect-req` | Detect implicit requirements |
| `swe-workflow-verify` | Verify implementation |
| `swe-workflow-research` | Code exploration/research |
| `swe-workflow-arch-review` | Architecture compliance review |

### Commands (9 total)
| Command | Purpose |
|---------|---------|
| `/swe-init` | Initialize SWE for project |
| `/swe-status` | Show workflow state |
| `/swe-reset` | Reset workflow state |
| `/swe-goto` | Force transition to state |
| `/swe-memory` | Manage session WM |
| `/swe-scaffold` | Scaffold new project |
| `/swe-sync` | Sync plugin memories |
| `/swe-cleanup` | Archive completed memories |
| `/swe-migrate` | Migrate legacy files |

### Agents (2 total)
| Agent | Purpose |
|-------|---------|
| `swe-init-agent` | Autonomous initialization |
| `swe-workflow-coordinator` | Swarm task coordination |

## Memories Organization

Memories are organized in subdirectories:

| Directory | Contents |
|-----------|----------|
| `memories/wf/` | 21 workflow state instructions (WF_*.md) |
| `memories/ref/` | Reference docs (REF_DEV_STANDARDS, REF_SWARM_PATTERNS, etc.) |
| `memories/claude/` | Claude behavior docs (CLAUDE.md, CLAUDE_OBLIGATIONS.md) |
| `memories/arch/` | Architecture documentation (ARCH_SWE.md) |
| `memories/dom/` | Domain documentation (DOM_SWE_HOOKS.md) |
| `memories/feature/` | Feature configs (FEATURE_SWE.md) |
| `memories/index/` | Index files (if any) |

## Plan Mode Triggers
| Mode | States |
|------|--------|
| Always | WF_PLAN_ARCHITECTURE, WF_ARCH_REVIEW, WF_SWARM_ORCHESTRATE |
| Never | WF_DEBUG_TDD, WF_CHECKPOINT, WF_VERIFY, WF_DONE, WF_CLEANUP, WF_RESEARCH, WF_EXECUTE |
| Conditional | WF_CLASSIFY (complexity >= medium), WF_DETECT_REQ (architectural) |

## RLVR Learning
| Signal Type | States | Impact |
|-------------|--------|--------|
| trajectory_init | WF_START | baseline |
| routing_decision | WF_CLASSIFY | neutral |
| clarify_visit | WF_CLARIFY | penalty (-0.1) |
| arch_review | WF_ARCH_REVIEW | bonus (+0.1) |
| verify_check | WF_VERIFY | bonus if first try (+0.1) |
| learning_checkpoint | WF_DONE | mandatory |

## Scripts
| Script | Purpose |
|--------|---------|
| `bump-version.sh` | Version management |
| `install-hooks.sh` | Install git hooks |
| `pre-commit` | Pre-commit validation |

## Dependencies
- **Internal:** Serena MCP (memory), Claude-Flow MCP (swarm/learning), RUV-Swarm MCP (DAA)
- **External:** jq (JSON parsing), bash, python3

## Runtime Files
| File | Purpose |
|------|---------|
| `.claude/workflow-state.json` | Current state, trajectory, rewards |
| `.claude/swe-setup-complete.json` | Setup completion flag |
| `.claude/learning.json` | RLVR configuration |

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
**Path:** `.serena/memories/`

Contains project-specific adaptations:
- `wf/WF_*.md` - Copied from plugin, may have project customizations
- `ref/REF_*.md` - Project-specific references
- `dom/DOM_SWE_*.md` - Domain documentation
- `feature/FEATURE_SWE.md` - This file
- `WM_*.md` - Session state

### Change Decision Matrix

| Change Type | Plugin Folder | Local Memories | Example |
|-------------|---------------|----------------|---------|
| Generic workflow logic | ✅ YES | ✅ SYNC | New WF_* state |
| Generic hook behavior | ✅ YES | ❌ No | Hook pattern change |
| Project-specific patterns | ❌ No | ✅ YES | Custom DOM_* doc |
| New skill/command | ✅ YES | ❌ No | New /swe-* command |
| Reference documentation | ✅ YES | ✅ SYNC | REF_* updates |
| Hook script changes | ✅ YES | ❌ No | Python hook edits |

### Hook Loading

**SWE hooks load automatically from the plugin folder** via Claude Code's plugin system. The `${CLAUDE_PLUGIN_ROOT}` variable in `hooks/hooks.json` is resolved automatically - no copying to settings.json needed.

See `DOM_SWE_HOOKS` for hook architecture details.

## Related Memories
- [ARCH_SWE](ARCH_SWE) - SWE architecture documentation
- [REF_SWE_DEVELOPMENT](REF_SWE_DEVELOPMENT) - Development standards
- [DOM_SWE_HOOKS](DOM_SWE_HOOKS) - Hook architecture
