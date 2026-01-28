# WF_INITIAL_SETUP

> **🔧 On step WF_INITIAL_SETUP**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

First-time plugin setup - install MCPs, configure environment.

## Entry

- **From**: SessionStart
- **Triggers**: missing_mcp, first_install, setup_incomplete

## Required Actions

1. `detect_missing_mcps` - Check for required MCP servers
2. `install_mcp_servers` - Install missing servers (serena, claude-flow)
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
|-----------|------------|
| complete | WF_START |
| issues | WF_CLARIFY |

## RLVR Signal

- **Type**: setup | **Impact**: neutral

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Setup complete | `WF_START` |
| Issues encountered | `WF_CLARIFY` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
