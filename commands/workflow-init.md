---
name: workflow-init
description: Initialize serena-workflow-engine plugin - first-time setup for new projects
---

# /workflow-init

First-time setup command for the serena-workflow-engine plugin. Run this when installing the plugin in a new project.

## When to Run

- First time using plugin in a project
- After cloning a repo with the plugin
- When `session-start.sh` reports "INITIAL SETUP REQUIRED"

## Setup Steps (7 total)

### Step 1: Detect Environment

Check current state:
```
Detecting environment...
  Project root: [cwd]
  Git repo: [yes/no]
  Existing .serena/: [yes/no]
  Existing .claude/: [yes/no]
```

### Step 2: Check MCP Servers

Verify required MCPs are available:

| MCP | Status | Required |
|-----|--------|----------|
| serena | [connected/missing] | MANDATORY |
| claude-flow | [connected/missing] | MANDATORY |
| ruv-swarm | [connected/missing] | MANDATORY |

**If any missing:**
```
================================================================================
SETUP: Missing MCP Servers
================================================================================
The following MCP servers are required but not configured:
  - [list missing]

[A] Auto-configure in ~/.claude.json (recommended)
[M] Show manual configuration
[X] Cancel setup
================================================================================
```

**Auto-configure adds to ~/.claude.json:**
```json
{
  "mcpServers": {
    "serena": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server", "--project", "./"]
    },
    "claude-flow": {
      "command": "npx",
      "args": ["claude-flow@alpha", "mcp", "start"]
    },
    "ruv-swarm": {
      "command": "npx",
      "args": ["ruv-swarm", "mcp", "start"]
    }
  }
}
```

**After configuring, prompt restart:**
```
================================================================================
RESTART REQUIRED
================================================================================
MCP servers configured. You must restart Claude Code.

1. Close this session (Ctrl+C or exit)
2. Reopen Claude Code
3. Return to this project
4. Run /workflow-init again

Setup will continue from Step 3.
================================================================================
```

### Step 3: Verify MCP Connections

After restart, verify all MCPs respond:
- Test `mcp__serena__list_memories`
- Test `mcp__claude-flow__system_status`
- Test `mcp__ruv-swarm__swarm_status`

### Step 4: Serena Onboarding

Run Serena's one-time project onboarding:
```javascript
const status = await mcp__serena__check_onboarding_performed();
if (!status.performed) {
  await mcp__serena__onboarding();
}
```

### Step 5: Create Core Memories

If missing, create from templates:

**_INDEX.md** (from templates/_INDEX_TEMPLATE.md)
**INDEX_FEATURES.md** (empty feature registry)
**ARCH_INDEX.md** (architecture placeholder)

### Step 6: Configure Gitignore

Add plugin entries to .gitignore:
```
# Claude Code Plugin - Local files
CLAUDE.local.md
.claude/settings.local.json
.claude/workflow-state.json
.claude/setup-state.json
.claude/setup-complete.json

# Runtime directories
**/.claude-flow
**/.swarm

# Session memories
.serena/memories/WORKING_MEMORY_*.md
.serena/archive-memories/
.serena/archive-specs/
```

### Step 7: Mark Setup Complete

Create `.claude/setup-complete.json`:
```json
{
  "complete": true,
  "timestamp": "[ISO date]",
  "mcps": ["serena", "claude-flow", "ruv-swarm"],
  "version": "1.0.0"
}
```

## Final Output

```
================================================================================
SETUP COMPLETE
================================================================================
Serena Workflow Engine initialized successfully.

  [x] MCP Servers: serena, claude-flow, ruv-swarm
  [x] Serena Onboarding: Complete
  [x] Core Memories: Created
  [x] Gitignore: Configured

Next steps:
  1. Run /onboard-feature [KEY] to register your first feature
  2. Or start working - workflow will guide you

Type any message to begin. Workflow starts at WF_START.
================================================================================
```

## Resuming Interrupted Setup

If setup was interrupted, `/workflow-init` detects state from:
- `.claude/setup-state.json` (tracks current step)
- Resumes from last incomplete step

## Troubleshooting

### MCP Won't Connect
```
1. Check uvx/npx installed: which uvx && which npx
2. Check ~/.claude.json syntax: cat ~/.claude.json | jq
3. View MCP logs: claude mcp logs [server-name]
4. Try manual start: uvx serena start-mcp-server --project ./
```

### Serena Language Server Error
```
Error: "language server manager not initialized"
Fix: rm -rf ~/.serena/language_servers/static/BashLanguageServer
Then restart Claude Code - Serena will reinstall automatically.
```
