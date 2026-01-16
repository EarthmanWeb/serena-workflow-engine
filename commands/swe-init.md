---
name: swe-init
description: Initialize serena-workflow-engine plugin - first-time setup for new projects
---

# /swe-init

First-time setup command for the serena-workflow-engine plugin. Run this when installing the plugin in a new project.

## When to Run

- First time using plugin in a project
- After cloning a repo with the plugin
- When `session-start.sh` reports "INITIAL SETUP REQUIRED"

## Setup Steps (9 total)

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
4. Run /swe-init again

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

### Step 5: Initialize Claude-Flow

Run claude-flow init with CLAUDE.md protection:

**Before init - backup existing CLAUDE.md:**
```bash
# Check if CLAUDE.md exists
if [ -f "CLAUDE.md" ]; then
  cp CLAUDE.md CLAUDE.md.backup
  echo "Backed up existing CLAUDE.md"
fi
```

**Run claude-flow init:**
```bash
npx claude-flow@alpha init
```

**After init - handle CLAUDE.md:**
```
================================================================================
CLAUDE.md HANDLING
================================================================================
Claude-flow created/modified CLAUDE.md.

[A] Keep claude-flow version (recommended for new projects)
[B] Restore original CLAUDE.md, save claude-flow version as CLAUDE_FLOW.md
[C] Merge: Keep original, append claude-flow content
[D] Discard claude-flow version, restore original
================================================================================
```

**Option B (typical for existing projects):**
```bash
mv CLAUDE.md CLAUDE_FLOW.md
mv CLAUDE.md.backup CLAUDE.md
echo "Original CLAUDE.md restored. Claude-flow config saved to CLAUDE_FLOW.md"
```

**Option C (merge):**
```bash
cat CLAUDE.md >> CLAUDE.md.backup
mv CLAUDE.md.backup CLAUDE.md
echo "Merged claude-flow content into existing CLAUDE.md"
```

### Step 6: Install Workflow Instructions

Copy instruction files from plugin to Serena memories using dynamic discovery:

```
PLUGIN_INSTRUCTIONS = ".claude/plugins/serena-workflow-engine/state-machine/instructions"

# Discover all WF_*.md files (no hardcoded list)
for each file in glob(PLUGIN_INSTRUCTIONS + "/WF_*.md"):
    memory_name = basename(file).replace('.md', '')
    content = read(file)
    mcp__serena__write_memory(memory_name, content)
    echo "  Installed: " + memory_name

# Verify
memories = mcp__serena__list_memories()
wf_count = count(memories starting with "WF_")
echo "Workflow instructions: " + wf_count + " installed"
```

**Expected**: All WF_* instruction files copied to Serena memories

### Step 7: Create Core Memories

If missing, create from templates:

**_INDEX.md** (from templates/_INDEX_TEMPLATE.md)
**INDEX_FEATURES.md** (empty feature registry)
**ARCH_INDEX.md** (architecture placeholder)

### Step 8: Configure Gitignore

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

### Step 9: Mark Setup Complete

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
  [x] Claude-Flow Initialized
  [x] Workflow Instructions: Installed
  [x] Core Memories: Created
  [x] Gitignore: Configured

Next steps:
  1. Run /onboard-feature [KEY] to register your first feature
  2. Or start working - workflow will guide you

Type any message to begin. Workflow starts at WF_START.
================================================================================
```

## Resuming Interrupted Setup

If setup was interrupted, `/swe-init` detects state from:
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
