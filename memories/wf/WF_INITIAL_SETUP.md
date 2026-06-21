# WF_INITIAL_SETUP

> **On step WF_INITIAL_SETUP**

---

## Purpose

First-time plugin setup - install MCPs, configure environment.

## Entry

- **From**: SessionStart
- **Triggers**: missing_mcp, first_install, setup_incomplete

## Required Actions

1. `detect_missing_mcps` - Check for required MCP servers
2. `install_mcp_servers` - Install missing servers (serena, ruflo)
3. `prompt_restart` - Request Claude Code restart if MCPs installed
4. `verify_installation` - Confirm MCPs are accessible
5. `run_serena_onboard` - Execute Serena project onboarding
6. `handle_claude_md` - Create/update CLAUDE.md with workflow entry point
7. `configure_gitignore` - Add workflow artifacts to .gitignore

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: never

## Transitions

| Condition | Next State |
| --------- | ---------- |
| complete  | WF_CLASSIFY |
| issues    | WF_CLARIFY |

## RLVR Signal

- **Type**: setup | **Impact**: neutral

## Routing

| Condition          | Read Next  |
| ------------------ | ---------- |
| Setup complete     | `WF_CLASSIFY` |
| Issues encountered | `WF_CLARIFY` |
