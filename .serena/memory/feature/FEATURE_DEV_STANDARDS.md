---
name: Development Standards
description: Project overview, per-language conventions, and build/format/git commands for serena-workflow-engine.
metadata:
  type: feature
---

# FEATURE_DEV_STANDARDS — Development Standards Index

## Project Overview

State-machine workflow engine plugin for Claude Code. Integrates Serena memory persistence, hook-driven event architecture, and optional swarm orchestration. Manages the SWE lifecycle through states (INIT, CLASSIFY, ARCH_REVIEW, EXECUTE, VERIFY, DONE, …). Transitions are explicit (`set_state` / prompt-intent hook) — reading a WF_* memory does NOT advance the FSM. Authoritative state list: `state-machine/states.json` (see `mem:dom/DOM_SWE_STATE_MACHINE`).

**Tech stack:** Python (hooks, bootstrap, MCP servers) · Markdown (memories, specs, workflow defs) · JSON (config, state machine) · npm (dprint dev dep only) · dprint (markdown/JSON format) · MCP servers: Serena (code intelligence), swe-wm (working memory).

**Entry points:**
- Plugin manifest: `.claude-plugin/plugin.json`
- Hook registry: `hooks/hooks.json` (SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop)
- Hook scripts: `hooks/{pre,post,prompt,session,stop}/*.py`
- Commands/skills: `commands/`, `skills/`
- Agents: `agents/` (e.g. `swe-init-agent.md`)
- Bundled plugin memories (source of truth, shipped read-only): `memories/`
- Scripts: `scripts/` (bootstrap, version bump, serena start)
- State machine: `state-machine/states.json`

**Naming conventions:**
- Memory files: `UPPER_SNAKE_CASE.md` (`WF_INIT.md`, `FEATURE_TESTS.md`).
- Feature keys: `FEATURE_[KEY]`.
- Hook scripts: `lower_snake_case.py` (`swe_session_start.py`).
- Skill/command dirs: `kebab-case`.

## Standards by Language

| Language | Memory | Status |
| --- | --- | --- |
| Python | `DEV_PYTHON` | Not created — create when needed |

### Python
- Shebang `#!/usr/bin/env python3`.
- Prefer standard library (json, os, sys, pathlib, subprocess).
- snake_case functions; UPPER_SNAKE_CASE constants.
- Hooks: ALWAYS output JSON to STDOUT, ALWAYS exit 0. NEVER exit 1. (See `mem:dom/DOM_SWE_HOOKS`.)

### Markdown
- Format with dprint (`npm run fmt`).
- Memories follow `mem:ref/REF_MEMORY_STYLE` (terse, imperative, front-matter first).

### JSON
- dprint, 2-space indent.

## Commands

| Purpose | Command |
| --- | --- |
| Format | `npm run fmt` |
| Format check | `npm run fmt:check` |
| Version bump | `bash scripts/bump-version.sh` |
| Install hooks (local dev) | `bash scripts/install-hooks.sh` |
| Start Serena MCP | `bash scripts/start-serena.sh` |
| Start WM MCP | `bash scripts/start-wm-mcp.sh` |
| Bootstrap a target project | `python3 scripts/swe-bootstrap.py` |

Package manager: npm (dprint only). Main branch: `main` (PR target).

## General Standards

- Fail fast with clear errors. NEVER add silent failures or empty catch blocks. (See CLAUDE_OBLIGATIONS "Let It Fail".)
- New files follow existing directory structure and casing.
- New functional code requires tests (see `mem:feature/FEATURE_TESTS`).

## Design Patterns

- Hook-driven: all workflow logic triggered by Claude Code hooks.
- State machine: transitions declared in `state-machine/states.json`.
- Serena memories: cross-session persistence. swe-wm MCP: per-session ephemeral state.
