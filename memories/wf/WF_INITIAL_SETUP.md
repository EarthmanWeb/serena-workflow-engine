---
name: WF_INITIAL_SETUP
description: First-time plugin setup — install MCPs, configure environment, then route to WF_CLASSIFY or WF_CLARIFY.
metadata:
  type: workflow
---

# WF_INITIAL_SETUP

> **On step WF_INITIAL_SETUP**

## Entry

- Enter from `SessionStart`.
- Triggers: `missing_mcp`, `first_install`, `setup_incomplete`.

## Permissions

- Edit: NEVER. Write: NEVER.
- Plan Mode: NEVER.

## Required Actions

Run in order:

1. `detect_missing_mcps` — check for required MCP servers.
2. `install_mcp_servers` — install missing servers (serena, ruflo).
3. `prompt_restart` — request Claude Code restart when MCPs installed.
4. `verify_installation` — confirm MCPs are accessible.
5. `run_serena_onboard` — execute Serena project onboarding.
6. `handle_claude_md` — create/update CLAUDE.md with workflow entry point.
7. `configure_gitignore` — add workflow artifacts to `.gitignore`.

## RLVR Signal

- Type: `setup`. Impact: `neutral`.

## Routing

| Condition          | Read Next     |
| ------------------ | ------------- |
| Setup complete     | `WF_CLASSIFY` |
| Issues encountered | `WF_CLARIFY`  |
