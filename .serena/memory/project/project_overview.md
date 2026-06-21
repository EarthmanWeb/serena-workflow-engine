# Serena Workflow Engine - Project Overview

## Purpose
A 13-state workflow engine plugin for Claude Code (13 state nodes plus the WF_INIT entry pseudo-state) that integrates with Serena memory persistence, hook-driven event architecture, and optional swarm orchestration. It manages the software engineering lifecycle through structured states (INIT, CLASSIFY, ARCH_REVIEW, EXECUTE, VERIFY, DONE, etc.). Transitions are explicit (via set_state / the prompt-intent hook) — reading a WF_* memory does NOT advance the FSM.

## Tech Stack
- **Runtime:** Claude Code CLI plugin system
- **Languages:** Python (hook scripts, bootstrap, MCP servers), TypeScript/JavaScript (hooks JSON, dprint formatting), Markdown (memories, specs, workflow definitions)
- **Package manager:** npm (for dprint dev dependency)
- **MCP Servers:** Serena (code intelligence), swe-wm (working memory state management)
- **Formatting:** dprint (markdown/JSON formatting)
- **State machine:** JSON-defined state transitions in `state-machine/`

## Architecture
- **Plugin root:** `.claude-plugin/plugin.json` defines the plugin
- **Hooks:** `hooks/hooks.json` registers SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop hooks
- **Hook scripts:** Python scripts in `hooks/` subdirectories (pre/, post/, prompt/, session/, stop/)
- **Skills:** Slash commands in `skills/` (swe-init, swe-status, swe-feature-onboard, etc.)
- **Agents:** Agent definitions in `agents/` (swe-init-agent.md)
- **Memories:** Workflow/feature/reference memories in `memories/` (read-only plugin memories)
- **Scripts:** Bootstrap, version bump, Serena start scripts in `scripts/`
- **Commands:** CLI command definitions in `commands/`

## Key Directories
```
.claude-plugin/       # Plugin manifest
hooks/                # Hook scripts (Python) and hooks.json
skills/               # Slash command definitions
agents/               # Agent prompt definitions
memories/             # Plugin bundled memories (read-only)
scripts/              # Utility scripts (bootstrap, install, etc.)
commands/             # CLI command definitions
state-machine/        # State transition definitions
vscode-ext/           # Serena Log Viewer VSCode extension
```

## Per-Project Runtime Directories (created by bootstrap)
```
.serena/memory/       # Project memories (features, domain, refs, specs)
.serena/memories/     # Working Memory files (per-session)
.serena/swe-state/    # Authoritative workflow state files
.serena/streams/      # Append-only event logs
```
