# FEATURE_SWE - Serena Workflow Engine

## Overview
- **Name:** Serena Workflow Engine
- **Type:** plugin
- **Language:** Bash/JSON/Markdown
- **Framework:** Claude Code Plugins
- **Root Path:** `.claude/plugins/serena-workflow-engine`

## Architecture

### Layers
| Layer | Purpose | Directory | Pattern |
|-------|---------|-----------|---------|
| State Machine | 21-state workflow engine | `state-machine/` | FSM with transitions |
| Hooks | Event handlers for Claude Code | `hooks/` | Shell scripts |
| Skills | User-invocable workflows | `skills/` | YAML frontmatter + MD |
| Commands | CLI shortcuts | `commands/` | Markdown |
| Templates | Memory scaffolds | `templates/` | Markdown |
| Agents | Swarm agent definitions | `agents/` | Markdown |

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

## Core Components

### States (21 total)
| Category | States |
|----------|--------|
| Setup | WF_INITIAL_SETUP, WF_ONBOARD |
| Entry | WF_START, WF_CLASSIFY, WF_CONTINUE |
| Analysis | WF_RESEARCH, WF_DETECT_REQ, WF_REQUIREMENT |
| Planning | WF_PLAN_ARCHITECTURE, WF_ARCH_REVIEW, WF_SWARM_ORCHESTRATE |
| Gates | WF_CLARIFY, WF_ASK_PERMISSION |
| Execution | WF_LOAD_FEATURE, WF_UPDATE_MEMORY, WF_EXECUTE, WF_CHECKPOINT, WF_DEBUG_TDD |
| Completion | WF_VERIFY, WF_DONE, WF_CLEANUP |

### Hooks (12 Python scripts)
| Hook | Trigger | Purpose |
|------|---------|---------|
| session_start.py | SessionStart | Initialize workflow state, RLVR trajectory |
| user_prompt_workflow.py | UserPromptSubmit | Initialize WF_START, transition state |
| user_prompt_swarm.py | UserPromptSubmit | Detect swarm keywords |
| claude_flow_pre_bash.py | PreToolUse (Bash) | Claude-Flow pre-command validation |
| pre_edit_validate.py | PreToolUse (Edit/Write/Serena) | Validate edit permissions |
| claude_flow_pre_edit.py | PreToolUse (Edit/Write/Serena) | Claude-Flow pre-edit integration |
| claude_flow_post_bash.py | PostToolUse (Bash) | Claude-Flow post-command learning |
| post_edit_checkpoint.py | PostToolUse (Edit/Write/Serena) | Track edits, trigger checkpoints |
| claude_flow_post_edit.py | PostToolUse (Edit/Write/Serena) | Claude-Flow post-edit learning |
| post_read_state.py | PostToolUse (read_memory) | State transitions, plan mode |
| post_task_learn.py | PostToolUse (read_memory) | RLVR learning |
| stop_workflow_check.py | Stop | Verify WF_DONE reached |

### Skills (11 total)
- swe-onboard-feature, swe-onboard-quick
- swe-scaffold-project
- swe-swarm-orchestrate, swe-swarm-analyze
- swe-workflow-debug-tdd, swe-workflow-detect-req
- swe-workflow-verify, swe-workflow-research
- swe-workflow-arch-review, swe-workflow-linter

### Commands (8 total)
- /swe-init, /swe-status, /swe-reset
- /swe-goto, /swe-memory, /swe-scaffold
- /swe-cleanup, /swe-migrate

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

## Domains (DOM_*)
- `DOM_SWE_STATE_MACHINE` - State transition logic
- `DOM_SWE_HOOKS` - Event handling patterns
- *RLVR documented in SYS_SWE_SWARM*

## Systems (SYS_*)
- `SYS_SWE_MEMORY` - Serena memory integration
- `SYS_SWE_SWARM` - Claude-Flow/RUV-Swarm coordination

## Dependencies
- **Internal:** Serena MCP (memory), Claude-Flow MCP (swarm/learning), RUV-Swarm MCP (DAA)
- **External:** jq (JSON parsing), bash

## Runtime Files
| File | Purpose |
|------|---------|
| `.claude/workflow-state.json` | Current state, trajectory, rewards |
| `.claude/setup-complete.json` | Setup completion flag |
| `.claude/learning.json` | RLVR configuration |

## Test Commands
```bash
# Validate state machine
jq . .claude/plugins/serena-workflow-engine/state-machine/states.json

# Check hook permissions
ls -la .claude/plugins/serena-workflow-engine/hooks/*.sh

# Verify plugin installation
claude plugin list | grep serena-workflow-engine
```

## ⚠️ Development Standards (Dual-Location Architecture)

SWE is a **standalone plugin** with a **dual-location architecture**:

### Location 1: Plugin Folder (Generic/Portable)
**Path:** `.claude/plugins/serena-workflow-engine/`

Contains files that should work across ANY project using the plugin:
- `state-machine/instructions/WF_*.md` - Workflow state instructions
- `state-machine/references/REF_*.md` - Generic reference docs
- `hooks/*.py` - Event handler scripts
- `hooks/hooks.json` - Hook configuration template
- `skills/*/SKILL.md` - Skill definitions
- `commands/*.md` - Command definitions
- `templates/*.md` - Memory templates
- `README.md` - Plugin documentation

### Location 2: Local Serena Memories (Project-Specific)
**Path:** `.serena/memories/`

Contains project-specific adaptations:
- `WF_*.md` - Copied from plugin, may have project customizations
- `REF_*.md` - Project-specific references
- `DOM_SWE_*.md` - Domain documentation
- `SYS_SWE_*.md` - System documentation
- `FEATURE_SWE.md` - This file
- `WORKING_MEMORY_*.md` - Session state

### Change Decision Matrix

| Change Type | Plugin Folder | Local Memories | Example |
|-------------|---------------|----------------|---------|
| Generic workflow logic | ✅ YES | ✅ SYNC | New WF_* state |
| Generic hook behavior | ✅ YES | ❌ No | Hook pattern change |
| Project-specific patterns | ❌ No | ✅ YES | Custom DOM_* doc |
| New skill/command | ✅ YES | ❌ No | New /swe-* command |
| Reference documentation | ✅ YES | ✅ SYNC | REF_* updates |
| Hook script changes | ✅ YES | ⚠️ settings.json | Python hook edits |

### ⚠️ CRITICAL: Hook Changes MUST Sync with settings.json

When modifying hooks:
1. **Edit hook script** in `.claude/plugins/serena-workflow-engine/hooks/`
2. **Update hooks.json** in same directory (uses `${CLAUDE_PLUGIN_ROOT}` paths)
3. **Update .claude/settings.json** (uses literal paths)
4. **Verify both configs match** in structure and matchers

See `DOM_SWE_HOOKS` for detailed sync requirements.

## Related Memories
- [INDEX_FEATURES](INDEX_FEATURES)
- [ARCH_INDEX](ARCH_INDEX)
- [WF_START](WF_START) - Entry point documentation
- [DOM_SWE_DEVELOPMENT](DOM_SWE_DEVELOPMENT) - Development standards
- [DOM_SWE_HOOKS](DOM_SWE_HOOKS) - Hook architecture
