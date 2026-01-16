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

### Step 5.5: Install SWE Hooks to Settings

VS Code extension reads hooks from `.claude/settings.json`, not from plugin's hooks.json. Copy SWE hooks to settings.json with relative paths.

**Read hooks from plugin and convert paths:**
```bash
# Get hooks configuration from plugin and convert ${CLAUDE_PLUGIN_ROOT} to relative path
cat .claude/plugins/serena-workflow-engine/hooks/hooks.json | \
  sed 's|\${CLAUDE_PLUGIN_ROOT}|.claude/plugins/serena-workflow-engine|g' | \
  jq '.hooks'
```

**Add hooks to .claude/settings.json:**
```bash
# Merge hooks into settings.json
if [ -f ".claude/settings.json" ]; then
  # Read existing settings and plugin hooks (with converted paths)
  EXISTING=$(cat .claude/settings.json)
  HOOKS=$(cat .claude/plugins/serena-workflow-engine/hooks/hooks.json | \
    sed 's|\${CLAUDE_PLUGIN_ROOT}|.claude/plugins/serena-workflow-engine|g' | \
    jq '.hooks')
  
  # Merge hooks into settings
  echo "$EXISTING" | jq --argjson hooks "$HOOKS" '. + {hooks: $hooks}' > .claude/settings.json.tmp
  mv .claude/settings.json.tmp .claude/settings.json
  echo "Installed SWE hooks to .claude/settings.json"
else
  # Create new settings.json with hooks
  HOOKS=$(cat .claude/plugins/serena-workflow-engine/hooks/hooks.json | \
    sed 's|\${CLAUDE_PLUGIN_ROOT}|.claude/plugins/serena-workflow-engine|g' | \
    jq '.hooks')
  echo "{\"hooks\": $HOOKS}" | jq '.' > .claude/settings.json
  echo "Created .claude/settings.json with SWE hooks"
fi
```

**Verify hooks installed:**
```bash
jq '.hooks | keys' .claude/settings.json
# Should show: ["PostToolUse", "PreToolUse", "SessionStart", "Stop", "UserPromptSubmit"]
```

### Step 5.6: Copy Workflow Instructions to Memories

Copy the state-machine instructions and references to `.serena/memories/` so the agent can access them via SERENA's `read_memory` instead of hooks echoing content.

**Copy instruction files:**
```bash
# Create memories directory if needed
mkdir -p .serena/memories

# Copy all instruction files (WF_* and CLAUDE_OBLIGATIONS)
for file in .claude/plugins/serena-workflow-engine/state-machine/instructions/*.md; do
  filename=$(basename "$file" .md)
  cp "$file" ".serena/memories/${filename}.md"
done

# Copy all reference files (REF_*)
for file in .claude/plugins/serena-workflow-engine/state-machine/references/*.md; do
  filename=$(basename "$file" .md)
  cp "$file" ".serena/memories/${filename}.md"
done

echo "Copied workflow instructions to .serena/memories/"
```

**Verify files copied:**
```bash
ls .serena/memories/WF_*.md | wc -l  # Should show ~21 workflow files
ls .serena/memories/REF_*.md | wc -l  # Should show reference files
ls .serena/memories/CLAUDE_OBLIGATIONS.md  # Should exist
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
  [x] SWE Hooks: Installed to .claude/settings.json
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
