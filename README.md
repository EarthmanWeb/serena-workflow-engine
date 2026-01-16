# Serena Workflow Engine

Claude Code plugin that codifies the WF_* state machine workflow system with RLVR learning.

## Features

- **21 Workflow States** - Complete state machine for software engineering tasks
- **RLVR Learning** - Reinforcement Learning with Verifiable Rewards
- **Auto Plan Mode** - Automatic switching between Plan and Agent modes
- **Swarm Coordination** - Multi-agent support via Claude-Flow and RUV-Swarm
- **Serena Integration** - Memory persistence and symbolic code tools

## Requirements (ALL MANDATORY)

| Dependency | Purpose |
|------------|---------|
| Serena MCP | Memory persistence, symbolic tools |
| Claude Flow MCP | Swarm orchestration, SONA learning |
| RUV-Swarm MCP | DAA learning agents, cognitive adaptation |
| jq CLI | JSON parsing in hooks |

## Installation

### Via Git Submodule
```bash
cd /path/to/project
git submodule add https://github.com/your-org/serena-workflow-engine .claude/plugins/serena-workflow-engine
git submodule update --init --recursive
chmod +x .claude/plugins/serena-workflow-engine/hooks/*.sh
```

### Manual Integration
Add hooks to `.claude/settings.local.json` (see SPEC_SWE_INSTALLATION).

## State Categories

| Category | States |
|----------|--------|
| Setup | WF_INITIAL_SETUP, WF_ONBOARD |
| Entry | WF_START, WF_CLASSIFY, WF_CONTINUE |
| Analysis | WF_RESEARCH, WF_DETECT_REQ, WF_REQUIREMENT |
| Planning | WF_PLAN_ARCHITECTURE, WF_ARCH_REVIEW, WF_SWARM_ORCHESTRATE |
| Gates | WF_CLARIFY, WF_ASK_PERMISSION |
| Execution | WF_LOAD_FEATURE, WF_UPDATE_MEMORY, WF_EXECUTE, WF_CHECKPOINT, WF_DEBUG_TDD |
| Completion | WF_VERIFY, WF_DONE, WF_CLEANUP |

## Commands

- `/workflow-status` - Display current state
- `/workflow-reset` - Reset workflow (requires confirmation)
- `/workflow-goto [STATE]` - Force state transition
- `/cleanup` - Archive completed work

## Skills

- `workflow-research` - Code exploration
- `workflow-verify` - Implementation verification
- `workflow-arch-review` - Architecture compliance
- `workflow-debug-tdd` - Test-driven debugging
- `workflow-detect-req` - Requirement detection
- `workflow-linter` - Code quality checks
- `onboard-feature` - Feature registration wizard
- `swarm-orchestrate` - Multi-agent coordination

## Exit Codes

| Code | Behavior |
|------|----------|
| 0 | Allow silently |
| 1 | Allow with message |
| 2 | Block operation |

## License

MIT
