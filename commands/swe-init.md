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
- [ ] Step 5.5: Remove Claude-Flow Hooks from Settings
- [ ] Step 5.6: Install SWE Hooks to settings.local.json
- [ ] Step 5.7: Install Instruction Files
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

**Note:** Steps are numbered 1-8 with substeps 5.5, 5.6, and 5.7. Step 9 is Final Verification.

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

### Step 5.5: Remove Claude-Flow Hooks from Settings

**IMPORTANT:** Claude-flow init adds its own hooks to `.claude/settings.json`. These conflict with the SWE plugin hooks (which are auto-loaded via the plugin system). Remove them.

**Remove claude-flow hooks:**
```bash
# Check if hooks exist in settings.json
if jq -e '.hooks' .claude/settings.json > /dev/null 2>&1; then
  # Remove hooks key from settings.json
  cat .claude/settings.json | jq 'del(.hooks)' > .claude/settings.json.tmp
  mv .claude/settings.json.tmp .claude/settings.json
  echo "Removed claude-flow hooks from settings.json"
else
  echo "No hooks to remove"
fi
```

**Why:** Claude-flow hooks in settings.json would conflict and cause "Workflow not initialized" errors.

**Verify hooks removed:**
```bash
jq '.hooks // "none"' .claude/settings.json
# Should show: "none"
```

### Step 5.6: Install SWE Hooks to settings.local.json (MANDATORY)

**⚠️ THIS STEP IS MANDATORY - Hooks do NOT auto-load from plugin**

Copy hooks from `hooks.json` to `settings.local.json`, translating paths:

```bash
# Path to plugin hooks.json
HOOKS_SRC=".claude/plugins/serena-workflow-engine/hooks/hooks.json"
SETTINGS_LOCAL=".claude/settings.local.json"

# Create settings.local.json if missing
if [ ! -f "$SETTINGS_LOCAL" ]; then
  echo '{}' > "$SETTINGS_LOCAL"
fi

# Extract hooks from hooks.json, translate paths, merge into settings.local.json
jq -s '
  # Take hooks from first file (hooks.json), rest of config from second (settings.local.json)
  .[0].hooks as $hooks |
  .[1] |
  .hooks = ($hooks | walk(
    if type == "string" then
      gsub("\\$\\{CLAUDE_PLUGIN_ROOT\\}"; ".claude/plugins/serena-workflow-engine")
    else .
    end
  ))
' "$HOOKS_SRC" "$SETTINGS_LOCAL" > "${SETTINGS_LOCAL}.tmp" && mv "${SETTINGS_LOCAL}.tmp" "$SETTINGS_LOCAL"

echo "Installed SWE hooks to settings.local.json"
```

**Verify hooks installed:**
```bash
jq '.hooks | keys' .claude/settings.local.json
# Should show: ["PostToolUse", "PreToolUse", "SessionStart", "Stop", "UserPromptSubmit"]
```

**Why this step exists:** Claude Code plugins do NOT auto-load hooks from hooks.json. The hooks must be explicitly copied to settings.local.json with literal paths.

### Step 5.7: Install ALL Instruction Files to Memories (MANDATORY)

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

# 2. Verify claude-flow hooks REMOVED from settings.json
echo "=== Claude-Flow Hooks Check ==="
if jq -e '.hooks' .claude/settings.json > /dev/null 2>&1; then
  echo "FAIL: claude-flow hooks still in settings.json - run Step 5.5"
else
  echo "PASS: No conflicting hooks in settings.json"
fi

# 2b. Verify SWE hooks INSTALLED in settings.local.json
echo "=== SWE Hooks Check ==="
if jq -e '.hooks.SessionStart' .claude/settings.local.json > /dev/null 2>&1; then
  echo "PASS: SWE hooks installed in settings.local.json"
else
  echo "FAIL: SWE hooks missing from settings.local.json - run Step 5.6"
fi

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
- [ ] Hooks: claude-flow hooks REMOVED from .claude/settings.json
- [ ] Hooks: SWE hooks INSTALLED in .claude/settings.local.json (SessionStart, etc.)
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
- SWE Hooks: Installed to .claude/settings.local.json
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
