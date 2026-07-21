---
name: Development Standards
description: Development standards index for serena-workflow-engine — project overview, per-language conventions, and commands
metadata:
  type: feature
---

# FEATURE_DEV_STANDARDS - Development Standards Index

## Project Overview

**Purpose:** A state-machine workflow engine plugin for Claude Code that integrates with Serena memory persistence, hook-driven event architecture, and optional swarm orchestration. It manages the software engineering lifecycle through structured states (INIT, CLASSIFY, ARCH_REVIEW, EXECUTE, VERIFY, DONE, etc.). Transitions are explicit (via set_state / the prompt-intent hook) — reading a WF_* memory does NOT advance the FSM. The authoritative state list lives in `state-machine/states.json` (enumerated in DOM_SWE_STATE_MACHINE).

**Tech Stack:**
- Runtime: Claude Code CLI plugin system
- Languages: Python (hook scripts, bootstrap, MCP servers), TypeScript/JavaScript (hooks JSON, dprint formatting), Markdown (memories, specs, workflow definitions)
- Package manager: npm (for dprint dev dependency)
- MCP Servers: Serena (code intelligence), swe-wm (working memory state management)
- Formatting: dprint (markdown/JSON formatting)
- State machine: JSON-defined state transitions in `state-machine/`

**Architecture / Entry Points:**
- Plugin root: `.claude-plugin/plugin.json` defines the plugin
- Hooks: `hooks/hooks.json` registers SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop hooks
- Hook scripts: Python scripts in `hooks/` subdirectories (pre/, post/, prompt/, session/, stop/)
- Skills/commands: Slash commands in `skills/` and `commands/`
- Agents: Agent definitions in `agents/` (e.g. swe-init-agent.md)
- Bundled memories: Read-only plugin memories in `memories/`
- Scripts: Bootstrap, version bump, Serena start scripts in `scripts/`

**Key Directories:**
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

**Class/File Naming Conventions:**
- Memory files: UPPER_SNAKE_CASE (e.g., `FEATURE_TESTS.md`, `WF_INIT.md`)
- Feature keys: `FEATURE_[KEY]` format
- Hook scripts: lowercase with underscores (e.g., `swe_session_start.py`)
- Skills directories: kebab-case (e.g., `swe-feature-onboard`)

## Project: serena-workflow-engine

**Primary Language:** python

## Standards by Language

<!-- Add DEV_* memories for each language used in the project -->

| Language               | Memory          | Status      |
| ---------------------- | --------------- | ----------- |
| python   | `DEV_PYTHON` | TODO: Create |

### Python

- Scripts use `#!/usr/bin/env python3` shebang
- Standard library preferred (json, os, sys, pathlib, subprocess)
- No type hints enforced in hook scripts (utility/glue code style)
- Functions use snake_case; constants use UPPER_SNAKE_CASE

### Markdown

- Formatted by dprint (`npm run fmt`)
- Memory files use structured headings and bullet lists
- Template memories use `FEATURE_` prefix convention

### JSON

- Formatted by dprint, 2-space indentation

## Commands

### Formatting
```bash
npm run fmt         # Format markdown and JSON files (dprint)
npm run fmt:check   # Check formatting without writing
```

### Version Management
```bash
bash scripts/bump-version.sh   # Bump plugin version
```

### Development Setup
```bash
bash scripts/install-hooks.sh  # Install hooks for local dev (git submodule)
bash scripts/start-serena.sh   # Start Serena MCP server
bash scripts/start-wm-mcp.sh   # Start Working Memory MCP server
```

### Bootstrap (per-project)
```bash
python3 scripts/swe-bootstrap.py   # Run bootstrap for a target project
```

### Package Management
- npm (dprint is the only dev dependency)

### Git
- Main branch: `main` (used for PRs)

## General Standards

### Code Style

- Follow existing project conventions (check existing files first)
- Use the project's configured linter/formatter if available
- Consistent naming: match the casing convention already in use

### File Organization

- New files follow existing directory structure patterns
- Group related functionality together
- Keep files focused on a single responsibility

### Error Handling

- Fail fast with clear error messages
- No silent failures or empty catch blocks
- Log errors at appropriate severity levels

### Testing

- See `FEATURE_TESTS` for test runner and patterns
- New functional code should have corresponding tests
- Follow existing test patterns in the project

### Design Patterns

- Hook-driven architecture: all workflow logic triggered by Claude Code hooks
- State machine pattern: transitions defined declaratively in JSON
- Memory persistence: Serena memories for cross-session state
- Working Memory: per-session ephemeral state via swe-wm MCP

## Per-Project Customization

1. **Create `DEV_*` memories** for each language (e.g., `DEV_PHP`, `DEV_PYTHON`)
2. **Add project-specific standards** (naming conventions, file headers, etc.)
3. **Document CI/CD requirements** (lint checks, coverage thresholds)
4. **Remove this section** after customization
