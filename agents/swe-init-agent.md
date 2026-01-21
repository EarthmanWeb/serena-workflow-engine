---
name: swe-init-agent
description: Autonomous SWE plugin initialization with verification
capabilities:
  - environment_detection
  - mcp_verification
  - settings_migration
  - hook_installation
  - memory_installation
---

# SWE Init Agent

Autonomous agent for initializing the serena-workflow-engine plugin. Completes all setup tasks and verifies success.

## Capabilities

1. **Environment Detection** - Check project state, git, existing directories
2. **MCP Verification** - Test serena, claude-flow, ruv-swarm respond
3. **Serena Onboarding** - Run one-time Serena setup
4. **Claude-Flow Init** - Initialize with CLAUDE.md protection
5. **Settings Migration** - Move claudeFlow config to settings.local.json
6. **Hook Management** - Remove from settings.json, install to settings.local.json
7. **Memory Installation** - Copy instruction files to .serena/memories/
8. **Verification** - Confirm all tasks completed correctly

## Agent Spawn

```javascript
Task({
  subagent_type: "general-purpose",
  description: "SWE plugin initialization",
  prompt: `[See TASKS section below]`
})
```

## TASKS

Execute ALL tasks (1-10, including 4b) in order, then verify.

### Task 1: Detect Environment
Report:
- Project root (cwd)
- Git repo status
- Existing .serena/ directory
- Existing .claude/ directory

### Task 2: Verify MCP Servers
Test these MCP tools respond:
- `mcp__plugin_serena-workflow-engine_serena__list_memories`
- `mcp__claude-flow__system_status`
- `mcp__plugin_serena-workflow-engine_ruv-swarm__swarm_status`

If any fail, report which ones and stop.

### Task 3: Serena Onboarding
```javascript
const status = await mcp__plugin_serena-workflow-engine_serena__check_onboarding_performed();
if (!status.performed) {
  await mcp__plugin_serena-workflow-engine_serena__onboarding();
}
```

### Task 4: Initialize Claude-Flow
```bash
# Backup existing CLAUDE.md
[ -f "CLAUDE.md" ] && cp CLAUDE.md CLAUDE.md.backup

# Run claude-flow init
npx claude-flow@alpha init

# Restore original CLAUDE.md if backup exists
[ -f "CLAUDE.md.backup" ] && mv CLAUDE.md CLAUDE_FLOW.md && mv CLAUDE.md.backup CLAUDE.md
```

### Task 4b: Review CLAUDE.md for Conflicting Workflow Commands
**Check CLAUDE.md for any workflow/session start instructions that conflict with SWE.**

Read CLAUDE.md and look for:
- References to `WF_START`, `WF_INIT`, or workflow initialization
- Instructions to read workflow memories on startup
- Session start procedures that duplicate SWE hooks

If found, remove them - SWE hooks handle workflow initialization automatically.

```bash
# Check for workflow conflicts in CLAUDE.md
if [ -f "CLAUDE.md" ]; then
  # Look for conflicting patterns
  if grep -qE "(WF_START|WF_INIT|read_memory.*WF_|workflow.*start|session.*start.*hook)" CLAUDE.md; then
    echo "Found potential workflow conflicts in CLAUDE.md - review and remove duplicates"
    grep -nE "(WF_START|WF_INIT|read_memory.*WF_|workflow.*start|session.*start.*hook)" CLAUDE.md
  else
    echo "No conflicting workflow commands in CLAUDE.md"
  fi
fi
```

If conflicts found, edit CLAUDE.md to remove the conflicting sections. SWE's SessionStart hook handles all workflow initialization.

### Task 5: Migrate Claude-Flow Settings to settings.local.json
**CRITICAL: Move claude-flow config from settings.json to settings.local.json**

```bash
SETTINGS=".claude/settings.json"
SETTINGS_LOCAL=".claude/settings.local.json"

# Create settings.local.json if missing
[ ! -f "$SETTINGS_LOCAL" ] && echo '{}' > "$SETTINGS_LOCAL"

# Extract and migrate statusLine and claudeFlow from settings.json to settings.local.json
jq -s '
  (.[0].statusLine // null) as $statusLine |
  (.[0].claudeFlow // null) as $claudeFlow |
  .[1] |
  (if $statusLine then .statusLine = $statusLine else . end) |
  (if $claudeFlow then .claudeFlow = $claudeFlow else . end)
' "$SETTINGS" "$SETTINGS_LOCAL" > "${SETTINGS_LOCAL}.tmp" && mv "${SETTINGS_LOCAL}.tmp" "$SETTINGS_LOCAL"

# Remove statusLine and claudeFlow from settings.json
jq 'del(.statusLine, .claudeFlow)' "$SETTINGS" > "${SETTINGS}.tmp" && mv "${SETTINGS}.tmp" "$SETTINGS"

echo "Migrated claudeFlow settings to settings.local.json"
```

### Task 6: Remove Claude-Flow Hooks from settings.json
```bash
if jq -e '.hooks' .claude/settings.json > /dev/null 2>&1; then
  jq 'del(.hooks)' .claude/settings.json > .claude/settings.json.tmp
  mv .claude/settings.json.tmp .claude/settings.json
  echo "Removed hooks from settings.json"
fi
```

### Task 7: Install SWE Hooks to settings.local.json
**CRITICAL: Use ABSOLUTE paths to avoid CWD-related path resolution bugs.**

The hooks in settings.local.json MUST use absolute paths. Relative paths like `.claude/plugins/...` will fail when the CWD changes during session resume or context compaction.

```bash
PROJECT_ROOT="$(pwd)"
HOOKS_SRC=".claude/plugins/serena-workflow-engine/hooks/hooks.json"
SETTINGS_LOCAL=".claude/settings.local.json"

# Replace ${CLAUDE_PLUGIN_ROOT} with ABSOLUTE path (not relative!)
jq -s --arg root "$PROJECT_ROOT" '
  .[0].hooks as $hooks |
  .[1] |
  .hooks = ($hooks | walk(
    if type == "string" then
      gsub("\\$\\{CLAUDE_PLUGIN_ROOT\\}"; ($root + "/.claude/plugins/serena-workflow-engine"))
    else .
    end
  ))
' "$HOOKS_SRC" "$SETTINGS_LOCAL" > "${SETTINGS_LOCAL}.tmp" && mv "${SETTINGS_LOCAL}.tmp" "$SETTINGS_LOCAL"

# Also fix any standalone relative paths in hook commands
jq --arg root "$PROJECT_ROOT" '
  .hooks |= walk(
    if type == "string" and startswith("python3 .claude/") then
      "python3 " + $root + "/" + ltrimstr("python3 ")
    elif type == "string" and startswith(".claude/") then
      $root + "/" + .
    else .
    end
  )
' "$SETTINGS_LOCAL" > "${SETTINGS_LOCAL}.tmp" && mv "${SETTINGS_LOCAL}.tmp" "$SETTINGS_LOCAL"

echo "Installed SWE hooks to settings.local.json with ABSOLUTE paths"
```

### Task 8: Install Instruction Files to Memories
```bash
mkdir -p .serena/memories .serena/memories/archived

cd .serena/memories
for f in WF_*.md CLAUDE_OBLIGATIONS.md DOM_SWE_*.md FEATURE_SWE.md REF_SWE_*.md; do
  [ -f "$f" ] && mv "$f" archived/"$f.$(date +%Y%m%d_%H%M%S).bak" 2>/dev/null
done
cd - >/dev/null

cp .claude/plugins/serena-workflow-engine/state-machine/instructions/*.md .serena/memories/

echo "Installed instruction files"
ls .serena/memories/{WF_*,CLAUDE_OBLIGATIONS,DOM_SWE_*,FEATURE_SWE,REF_SWE_*}.md 2>/dev/null | wc -l
```

### Task 9: Create Core Memories (if missing)
Check for and create if missing:
- `.serena/memories/_INDEX.md` (from templates/_INDEX_TEMPLATE.md)
- `.serena/memories/INDEX_FEATURES.md`

### Task 10: Configure Gitignore
Add these entries to .gitignore if not present:
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

## VERIFICATION

After all tasks, verify these 7 conditions:

1. **MCP Servers**: All three respond
2. **settings.json**: NO hooks, statusLine, or claudeFlow
   ```bash
   jq 'has("hooks"), has("statusLine"), has("claudeFlow")' .claude/settings.json
   # Expected: false false false
   ```
3. **settings.local.json**: HAS hooks, statusLine, and claudeFlow
   ```bash
   jq 'has("hooks"), has("statusLine"), has("claudeFlow")' .claude/settings.local.json
   # Expected: true true true
   ```
4. **SWE Hooks**: Correct keys installed
   ```bash
   jq '.hooks | keys' .claude/settings.local.json
   # Expected: ["PostToolUse", "PreToolUse", "SessionStart", "Stop", "UserPromptSubmit"]
   ```
4b. **Hook Paths Are Absolute**: All hook commands use absolute paths (not relative)
   ```bash
   # Check for relative paths - should return nothing
   jq -r '.. | .command? // empty' .claude/settings.local.json | grep -E "^python3 \\.claude/|^\\.claude/" || echo "OK: All paths are absolute"
   # If any relative paths found, re-run Task 7
   ```
5. **Instruction Files**: >= 26 files
   ```bash
   ls .serena/memories/ | grep -E "^(WF_|CLAUDE_OBLIGATIONS|DOM_SWE|FEATURE_SWE|REF_SWE)" | wc -l
   ```
6. **Core Memories**: _INDEX.md and INDEX_FEATURES.md exist
7. **Serena Onboarding**: Complete

## COMPLETION

Only after ALL verifications pass:

```bash
cat > .claude/setup-complete.json << 'EOF'
{
  "complete": true,
  "timestamp": "$(date -Iseconds)",
  "mcps": ["serena", "claude-flow", "ruv-swarm"],
  "version": "1.0.0",
  "verified": true
}
EOF
```

## Output Summary

```
**SETUP COMPLETE**

- MCP Servers: serena, claude-flow, ruv-swarm
- Serena Onboarding: Complete
- Claude-Flow: Initialized
- Settings Migration: claudeFlow config moved to settings.local.json
- SWE Hooks: Installed to settings.local.json
- Instruction Files: Copied to .serena/memories/
- Core Memories: Created
- Gitignore: Configured

**Next steps:**
1. Run /swe-onboard-feature [KEY] to register your first feature
2. Or start working - workflow will guide you
```

## Troubleshooting

### MCP Won't Connect
```bash
which uvx && which npx
cat ~/.claude.json | jq
claude mcp logs [server-name]
```

### Serena Language Server Error
```bash
rm -rf ~/.serena/language_servers/static/BashLanguageServer
# Then restart Claude Code
```

### Verification Fails
Identify which check failed, return to that task, fix, and re-verify.

### Hook Path Resolution Error (can't open file)
**Error:** `can't open file '/path/to/project/private/tests/.claude/plugins/...'`

**Cause:** Hook commands in settings.local.json use relative paths (`.claude/plugins/...`) that resolve from CWD. When session resumes after context compaction, CWD may be different.

**Fix:** Convert all relative paths to absolute paths in settings.local.json:
```bash
PROJECT_ROOT="/Users/webdev/LocalSites/sps/sps-wpms-refactor"  # Adjust for your project
jq --arg root "$PROJECT_ROOT" '
  .hooks |= walk(
    if type == "string" and (startswith("python3 .claude/") or startswith(".claude/")) then
      if startswith("python3 ") then
        "python3 " + $root + "/" + ltrimstr("python3 ")
      else
        $root + "/" + .
      end
    else .
    end
  )
' .claude/settings.local.json > .claude/settings.local.json.tmp && mv .claude/settings.local.json.tmp .claude/settings.local.json
```
