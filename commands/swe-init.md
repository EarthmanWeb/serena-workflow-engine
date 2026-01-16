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

### Step 5.5: Clean Up Claude-Flow Init Artifacts

Claude-flow init adds files that are managed elsewhere by the serena-workflow-engine plugin. Remove them to avoid conflicts.

**Remove root .mcp.json file:**
```bash
# Claude-flow init creates .mcp.json at project root
# This is managed by the plugin at .claude/plugins/serena-workflow-engine/.mcp.json
if [ -f ".mcp.json" ]; then
  rm .mcp.json
  echo "Removed root .mcp.json (managed by plugin)"
fi
```

**Remove hooks from settings files:**

Claude-flow init adds hooks to settings files, but these are managed by the serena-workflow-engine plugin.

**Clean up local project settings:**
```bash
# Remove hooks from .claude/settings.json if present
if [ -f ".claude/settings.json" ]; then
  # Use jq to remove the hooks key if it exists
  if command -v jq &> /dev/null; then
    jq 'del(.hooks)' .claude/settings.json > .claude/settings.json.tmp && \
      mv .claude/settings.json.tmp .claude/settings.json
    echo "Removed hooks from .claude/settings.json"
  else
    echo "WARNING: jq not installed - manually remove 'hooks' key from .claude/settings.json"
  fi
fi
```

**Clean up user-level settings (optional):**
```
================================================================================
HOOKS CLEANUP
================================================================================
Claude-flow may have added hooks to ~/.claude/settings.json

These hooks are managed by serena-workflow-engine and should be removed
from user settings to avoid conflicts.

[A] Auto-remove hooks from ~/.claude/settings.json (recommended)
[S] Skip - I'll manage hooks manually
[V] View hooks before deciding
================================================================================
```

**If Option A selected:**
```bash
# Remove hooks from ~/.claude/settings.json if present
if [ -f "$HOME/.claude/settings.json" ]; then
  if command -v jq &> /dev/null; then
    jq 'del(.hooks)' "$HOME/.claude/settings.json" > "$HOME/.claude/settings.json.tmp" && \
      mv "$HOME/.claude/settings.json.tmp" "$HOME/.claude/settings.json"
    echo "Removed hooks from ~/.claude/settings.json"
  else
    echo "WARNING: jq not installed - manually remove 'hooks' key from ~/.claude/settings.json"
  fi
fi
```

**If Option V selected:**
```bash
# Show current hooks in both files
echo "=== .claude/settings.json hooks ==="
jq '.hooks // "No hooks found"' .claude/settings.json 2>/dev/null || echo "File not found or invalid JSON"

echo "=== ~/.claude/settings.json hooks ==="
jq '.hooks // "No hooks found"' "$HOME/.claude/settings.json" 2>/dev/null || echo "File not found or invalid JSON"
```

### Step 6: Create Core Memories

If missing, create from templates:

**_INDEX.md** (from templates/_INDEX_TEMPLATE.md)
**INDEX_FEATURES.md** (empty feature registry)
**ARCH_INDEX.md** (architecture placeholder)

### Step 7: Configure Gitignore

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

### Step 8: Mark Setup Complete

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
  [x] Claude-Flow Cleanup: .mcp.json and hooks removed (managed by plugin)
  [x] Core Memories: Created
  [x] Gitignore: Configured

Next steps:
  1. Run /swe-onboard-feature [KEY] to register your first feature
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
