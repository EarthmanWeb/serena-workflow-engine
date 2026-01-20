---
name: swe-init
description: Initialize serena-workflow-engine plugin - first-time setup for new projects
---

# /swe-init

First-time setup command for the serena-workflow-engine plugin. Run this when installing the plugin in a new project.

---

## ⛔ CRITICAL: ALL STEPS ARE MANDATORY - DO NOT SKIP ANY

**Every step (1-9) MUST be executed in order. Skipping ANY step = broken installation.**

**Execution Rules:**
1. Execute EVERY step sequentially (1 → 2 → 3 → ... → 9)
2. Verify each step's output matches expected result before continuing
3. If a step fails, FIX IT before proceeding - do not skip
4. Step 9 (Final Verification) MUST pass before setup-complete.json is created
5. If Step 9 verification fails, identify failed step(s) and retry from there
6. **NO SHORTCUTS** - each step exists for a reason

**Checklist (mark as you complete):**
- [ ] Step 1: Detect Environment
- [ ] Step 2: Check MCP Servers
- [ ] Step 3: Verify MCP Connections
- [ ] Step 4: Serena Onboarding
- [ ] Step 5: Initialize Claude-Flow
- [ ] Step 5.5: Install SWE Hooks
- [ ] Step 5.6: Install Instruction Files
- [ ] Step 6: Create Core Memories
- [ ] Step 7: Configure Gitignore
- [ ] Step 8: Mark Setup Complete (ONLY after Step 9 passes)
- [ ] Step 9: Final Verification (MUST PASS)

---

## When to Run

- First time using plugin in a project
- After cloning a repo with the plugin
- When `session-start.sh` reports "INITIAL SETUP REQUIRED"

## Setup Steps (9 total + verification)

**Note:** Steps are numbered 1-8 with substeps 5.5 and 5.6. Step 9 is Final Verification.

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

**⚠️ SETUP: Missing MCP Servers**

The following MCP servers are required but not configured:
- [list missing]

Options:
- **[A]** Auto-configure in ~/.claude.json (recommended)
- **[M]** Show manual configuration
- **[X]** Cancel setup

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

**🔄 RESTART REQUIRED**

MCP servers configured. You must restart Claude Code.

1. Close this session (Ctrl+C or exit)
2. Reopen Claude Code
3. Return to this project
4. Run /swe-init again

Setup will continue from Step 3.

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

**📄 CLAUDE.md HANDLING**

Claude-flow created/modified CLAUDE.md.

Options:
- **[A]** Keep claude-flow version (recommended for new projects)
- **[B]** Restore original CLAUDE.md, save claude-flow version as CLAUDE_FLOW.md
- **[C]** Merge: Keep original, append claude-flow content
- **[D]** Discard claude-flow version, restore original

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

### Step 5.6: Install ALL Instruction Files to Memories (MANDATORY)

**⚠️ THIS STEP IS MANDATORY - DO NOT SKIP**

Copy OR merge EVERY file from `state-machine/instructions/` to Serena memories.

**Archive existing files first, then copy ALL instruction files:**
```bash
# Create directories
mkdir -p .serena/memories .serena/memories/archived

# Archive any existing files that will be overwritten
cd .serena/memories
for f in WF_*.md CLAUDE_OBLIGATIONS.md DOM_SWE_*.md FEATURE_SWE.md REF_SWE_*.md; do
  [ -f "$f" ] && mv "$f" archived/"$f.$(date +%Y%m%d_%H%M%S).bak"
done
cd - >/dev/null

# Copy ALL instruction files
cp .claude/plugins/serena-workflow-engine/state-machine/instructions/*.md .serena/memories/

echo "Installed instruction files:"
ls .serena/memories/{WF_*,CLAUDE_OBLIGATIONS,DOM_SWE_*,FEATURE_SWE,REF_SWE_*}.md 2>/dev/null | wc -l
```

**Expected: 26 files installed**

**Verify:**
```bash
ls .serena/memories/ | grep -E "^(WF_|CLAUDE_OBLIGATIONS|DOM_SWE|FEATURE_SWE|REF_SWE)" | wc -l
# Must be >= 26
```

**If any file is missing, STOP and reinstall before proceeding.**

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

### Step 9: Final Verification (MUST PASS BEFORE STEP 8)

**⛔ DO NOT create setup-complete.json until ALL verifications pass.**

Run these verification commands and confirm each one passes:

```bash
# 1. Verify MCP servers respond
echo "=== MCP Server Check ==="
# (Use mcp__serena__list_memories, mcp__claude-flow__system_status, mcp__ruv-swarm__swarm_status)

# 2. Verify hooks installed
echo "=== Hooks Check ==="
jq '.hooks | keys' .claude/settings.json 2>/dev/null || echo "FAIL: No hooks in settings.json"
# Expected: ["PostToolUse", "PreToolUse", "SessionStart", "Stop", "UserPromptSubmit"]

# 3. Verify instruction files installed (must be >= 26)
echo "=== Instruction Files Check ==="
INST_COUNT=$(ls .serena/memories/ | grep -E "^(WF_|CLAUDE_OBLIGATIONS|DOM_SWE|FEATURE_SWE|REF_SWE)" | wc -l | tr -d ' ')
echo "Instruction files: $INST_COUNT"
[ "$INST_COUNT" -ge 26 ] && echo "PASS" || echo "FAIL: Expected >= 26 files"

# 4. Verify core memories exist
echo "=== Core Memories Check ==="
[ -f ".serena/memories/_INDEX.md" ] && echo "PASS: _INDEX.md" || echo "FAIL: Missing _INDEX.md"
[ -f ".serena/memories/INDEX_FEATURES.md" ] && echo "PASS: INDEX_FEATURES.md" || echo "FAIL: Missing INDEX_FEATURES.md"

# 5. Verify gitignore entries
echo "=== Gitignore Check ==="
grep -q "CLAUDE.local.md" .gitignore && echo "PASS: gitignore configured" || echo "FAIL: Missing gitignore entries"

# 6. Verify Serena onboarding
echo "=== Serena Onboarding Check ==="
# (Use mcp__serena__check_onboarding_performed)
```

**Verification Checklist:**
- [ ] MCP servers: serena, claude-flow, ruv-swarm all respond
- [ ] Hooks: 5 hook types installed in .claude/settings.json
- [ ] Instructions: >= 26 WF_*/CLAUDE_OBLIGATIONS/etc files in .serena/memories/
- [ ] Core memories: _INDEX.md and INDEX_FEATURES.md exist
- [ ] Gitignore: Plugin entries added
- [ ] Serena: Onboarding complete

**If ANY verification fails:**
1. Identify which step created that artifact
2. Return to that step and re-execute
3. Re-run Step 9 verification
4. Only proceed to Step 8 when ALL pass

---

### Step 8: Mark Setup Complete

**⚠️ ONLY execute this step after Step 9 passes ALL verifications.**

Create `.claude/setup-complete.json`:
```json
{
  "complete": true,
  "timestamp": "[ISO date]",
  "mcps": ["serena", "claude-flow", "ruv-swarm"],
  "version": "1.0.0",
  "verified": true
}
```

## Final Output

Output this message directly (not in a code block):

**✅ SETUP COMPLETE**

Serena Workflow Engine initialized successfully.

- MCP Servers: serena, claude-flow, ruv-swarm
- Serena Onboarding: Complete
- Claude-Flow Initialized
- SWE Hooks: Installed to .claude/settings.json
- Workflow Instructions: Copied to .serena/memories/
- Core Memories: Created
- Gitignore: Configured

**Next steps:**
1. Run `/swe-onboard-feature [KEY]` to register your first feature
2. Or start working - workflow will guide you

Type any message to begin. Workflow starts at WF_START.

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
