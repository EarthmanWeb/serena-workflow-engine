---
name: swe-init-agent
description: Autonomous SWE plugin initialization with verification
capabilities:
  - environment_detection
  - mcp_verification
  - lsp_verification
  - settings_migration
  - hook_installation
  - memory_installation
---

# SWE Init Agent

Autonomous agent for initializing the swe plugin. Completes all setup tasks and verifies success.

## Capabilities

1. **Environment Detection** - Check project state, git, existing directories
2. **MCP Verification** - Test serena, claude-flow, ruv-swarm respond
3. **Serena Onboarding** - Run one-time Serena setup
4. **Claude-Flow Verification** - Verify plugin is installed
5. **Settings Migration** - Move claudeFlow config to settings.local.json
6. **Plugin Verification** - Verify SWE plugin is enabled
7. **Memory Installation** - Copy instruction files to .serena/swe/
8. **Verification** - Confirm all tasks completed correctly

## Agent Spawn

```javascript
Task({
  subagent_type: "general-purpose",
  description: "SWE plugin initialization",
  prompt: `[See TASKS section below]`,
});
```

## TASKS

Execute ALL tasks (1-11) in order, then verify.

### Task 1: Detect Environment

Report:

- Project root (cwd)
- Git repo status
- Existing .serena/ directory
- Existing .claude/ directory

### Task 2: Verify MCP Servers

Test these MCP tools respond:

- `mcp__plugin_swe_serena__list_memories`
- `mcp__claude-flow__system_status`
- `mcp__plugin_swe_ruv-swarm__swarm_status`

If any fail, report which ones and stop.

### Task 3: Serena Onboarding

```javascript
const status = await mcp__plugin_swe_serena__check_onboarding_performed();
if (!status.performed) {
  await mcp__plugin_swe_serena__onboarding();
}
```

### Task 4: Verify and Install Language Servers

**Check which LSP servers are available for languages configured in project.yml.**

```zsh
#!/usr/bin/env zsh
# NOTE: Uses zsh for associative arrays (macOS ships bash 3.x which lacks declare -A)

PROJECT_YML=".serena/project.yml"
if [ ! -f "$PROJECT_YML" ]; then
  echo "No project.yml found - skipping LSP check"
  exit 0
fi

typeset -A LSP_COMMANDS LSP_INSTALL

LSP_COMMANDS=(
  ruby      "ruby-lsp"
  markdown  "marksman"
  php       "intelephense"
  typescript "typescript-language-server"
  bash      "bash-language-server"
  python    "pylsp"
  yaml      "yaml-language-server"
)

LSP_INSTALL=(
  ruby      "gem install ruby-lsp"
  markdown  "brew install marksman"
  php       "npm install -g intelephense"
  typescript "npm install -g typescript-language-server typescript"
  bash      "npm install -g bash-language-server"
  python    "pipx install python-lsp-server"
  yaml      "npm install -g yaml-language-server"
)

MISSING=()
INSTALLED=()

for lang in ${(k)LSP_COMMANDS}; do
  cmd="${LSP_COMMANDS[$lang]}"
  if whence "$cmd" > /dev/null 2>&1; then
    INSTALLED+=("$lang ($cmd)")
  else
    MISSING+=("$lang")
  fi
done

echo "=== LSP Server Status ==="
for item in $INSTALLED; do
  echo "  ✅ $item"
done
for lang in $MISSING; do
  echo "  ❌ $lang - not found (install: ${LSP_INSTALL[$lang]})"
done

if [ ${#MISSING[@]} -gt 0 ]; then
  echo ""
  echo "Installing missing LSP servers..."
  for lang in $MISSING; do
    echo "  → Installing $lang: ${LSP_INSTALL[$lang]}"
    eval "${LSP_INSTALL[$lang]}" 2>&1 || echo "  ⚠️ Failed to install $lang LSP"
  done
  echo ""
  echo "Re-checking after install..."
  for lang in $MISSING; do
    cmd="${LSP_COMMANDS[$lang]}"
    if whence "$cmd" > /dev/null 2>&1; then
      echo "  ✅ $lang ($cmd) - now installed"
    else
      echo "  ❌ $lang ($cmd) - still missing (manual install needed)"
    fi
  done
fi
```

Install missing LSP servers automatically. If any fail to install, log the failure but do NOT block init — Serena is fault-tolerant and will work with partial LSP coverage.

**Note:** Uses `zsh` (not bash) for macOS compatibility. macOS ships bash 3.x which lacks associative arrays.

### Task 5: Verify Claude-Flow Plugin Installation

**Check if the claude-flow plugin is installed. If not, guide user to install it.**

```bash
# Check if claude-flow plugin is installed
if claude plugin list 2>/dev/null | grep -q "claude-flow@claude-flow-plugin"; then
  echo "✅ Claude-Flow plugin is installed"
else
  echo "⚠️ Claude-Flow plugin NOT installed"
  echo ""
  echo "The SWE plugin works best with Claude-Flow. Please install it:"
  echo ""
  echo "  claude plugin marketplace add https://github.com/EarthmanWeb/claude-flow-plugin.git#plugin"
  echo "  claude plugin install claude-flow@claude-flow-plugin --scope local"
  echo ""
  echo "Then restart Claude Code and run /swe-init again."
  echo ""
  echo "See the README for full installation instructions:"
  echo "  .claude/plugins/serena-workflow-engine/README.md"
  exit 1
fi
```

### Task 6: Review CLAUDE.md for Conflicting Workflow Commands

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

### Task 7: Migrate Claude-Flow Settings to settings.local.json

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

### Task 8: Verify SWE Plugin is Enabled

**SWE hooks load directly from the plugin folder - no copying needed.**

The plugin's `hooks/hooks.json` uses `${CLAUDE_PLUGIN_ROOT}` which is automatically resolved by Claude Code's plugin system.

```bash
SETTINGS_LOCAL=".claude/settings.local.json"

# Ensure plugin is enabled in settings.local.json
if ! jq -e '.enabledPlugins["swe@EarthmanWeb"] == true' "$SETTINGS_LOCAL" > /dev/null 2>&1; then
  jq '.enabledPlugins["swe@EarthmanWeb"] = true' "$SETTINGS_LOCAL" > "${SETTINGS_LOCAL}.tmp" && mv "${SETTINGS_LOCAL}.tmp" "$SETTINGS_LOCAL"
  echo "Enabled SWE plugin"
else
  echo "SWE plugin already enabled"
fi

# Verify hooks.json exists in plugin
if [ -f ".claude/plugins/serena-workflow-engine/hooks/hooks.json" ]; then
  echo "Plugin hooks.json found - hooks will load automatically"
  jq '.hooks | keys' .claude/plugins/serena-workflow-engine/hooks/hooks.json
else
  echo "ERROR: Plugin hooks.json missing!"
  exit 1
fi
```

### Task 9: Install Instruction Files to Memories

**IMPORTANT: This plugin uses a forked version of Serena that supports subdirectory organization.**

Memory files are organized in subdirectories and MUST be copied preserving this structure:

- `wf/` - Workflow state instructions (WF_*.md)
- `claude/` - Claude behavior docs (CLAUDE.md, CLAUDE_OBLIGATIONS.md)
- `ref/` - Reference documentation (REF_*.md)
- `dom/` - Domain documentation (DOM_*.md)
- `feature/` - Feature configurations (FEATURE_*.md)
- `arch/` - Architecture documentation (ARCH_*.md)
- `index/` - Index files (INDEX_*.md)

```bash
# Create directory structure (preserving subdirectory organization)
mkdir -p .serena/swe/{wf,claude,ref,dom,feature,arch,index,archived}

# Archive existing files in subdirectories
cd .serena/swe
for dir in wf claude ref dom feature arch; do
  if [ -d "$dir" ]; then
    for f in "$dir"/*.md; do
      [ -f "$f" ] && mv "$f" archived/"$(basename "$f").$(date +%Y%m%d_%H%M%S).bak" 2>/dev/null
    done
  fi
done
cd - >/dev/null

# Recursively copy ALL memories preserving directory structure
cp -r .claude/plugins/serena-workflow-engine/memories/* .serena/swe/

echo "Installed instruction files with directory structure"
echo "Subdirectories:"
ls -d .serena/swe/*/ 2>/dev/null
echo "Total files:"
find .serena/swe -name "*.md" -type f | wc -l
```

### Task 10: Create and Customize Core Memories

Check for and create if missing:

- `.serena/swe/_INDEX.md` (from memories/_INDEX.md)
- `.serena/swe/INDEX_FEATURES.md`

**IMPORTANT: Customize _INDEX.md after copying:**

1. List actual FEATURE_* files in `## Active Features` section
2. Remove the `<!-- TEMPLATE: ... -->` comment block
3. Clear placeholder text from `## Current Session`

```bash
# Copy _INDEX if missing
[ ! -f ".serena/swe/_INDEX.md" ] && cp .claude/plugins/serena-workflow-engine/memories/_INDEX.md .serena/swe/

# List existing FEATURE_* files to populate Active Features
echo "Available features to add to _INDEX:"
ls .serena/swe/FEATURE_*.md 2>/dev/null | xargs -I{} basename {} .md
```

Then edit `.serena/swe/_INDEX.md`:

- Replace `[FEATURE_X](FEATURE_X) - Description` with actual features
- Remove template comment block

### Task 11: Configure Gitignore

Add these entries to .gitignore if not present:

```
# Claude Code Plugin - Local files
CLAUDE.local.md
.claude/settings.local.json
.claude/workflow-state.json
.claude/setup-state.json
.claude/swe-setup-complete.json

# Runtime directories
**/.claude-flow
**/.swarm

# Session memories
.serena/swe/WM_*.md
.serena/archive-memories/
.serena/archive-specs/
```

## VERIFICATION

After all tasks, verify these 8 conditions:

1. **MCP Servers**: All three respond
2. **settings.json**: NO hooks, statusLine, or claudeFlow
   ```bash
   jq 'has("hooks"), has("statusLine"), has("claudeFlow")' .claude/settings.json
   # Expected: false false false
   ```
3. **settings.local.json**: HAS statusLine and claudeFlow (hooks load from plugin)
   ```bash
   jq 'has("statusLine"), has("claudeFlow")' .claude/settings.local.json
   # Expected: true true
   ```
4. **SWE Plugin Enabled**: Plugin is active
   ```bash
   jq '.enabledPlugins["swe@EarthmanWeb"]' .claude/settings.local.json
   # Expected: true
   ```
5. **Plugin Hooks Exist**: hooks.json in plugin folder
   ```bash
   jq '.hooks | keys' .claude/plugins/serena-workflow-engine/hooks/hooks.json
   # Expected: ["PostToolUse", "PreToolUse", "SessionStart", "Stop", "UserPromptSubmit"]
   ```
6. **Instruction Files**: >= 26 files with subdirectory structure
   ```bash
   # Verify subdirectories exist
   ls -d .serena/swe/{wf,claude,ref,dom,feature,arch}/ 2>/dev/null && echo "✅ Subdirectories exist"
   # Count total instruction files
   find .serena/swe -name "*.md" -type f | wc -l
   ```
7. **Core Memories**: _INDEX.md and INDEX_FEATURES.md exist
8. **Serena Onboarding**: Complete

## COMPLETION

Only after ALL verifications pass:

```bash
# Read version from plugin.json
PLUGIN_VERSION=$(jq -r '.version' .claude/plugins/serena-workflow-engine/.claude-plugin/plugin.json)

cat > .claude/swe-setup-complete.json << EOF
{
  "complete": true,
  "timestamp": "$(date -Iseconds)",
  "mcps": ["serena", "claude-flow", "ruv-swarm"],
  "version": "${PLUGIN_VERSION}",
  "verified": true
}
EOF
```

## Output Summary

```
**SETUP COMPLETE**

- MCP Servers: serena, claude-flow, ruv-swarm
- Serena Onboarding: Complete
- Claude-Flow Plugin: Verified installed
- Settings Migration: claudeFlow config moved to settings.local.json
- SWE Plugin: Enabled (hooks load from plugin folder)
- Instruction Files: Copied to .serena/swe/
- Core Memories: Created
- Gitignore: Configured

**Next steps:**
1. Run /swe-feature-onboard [KEY] to register your first feature
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

### Hooks Not Firing

**Cause:** Plugin not enabled or hooks.json missing.

**Fix:**

```bash
# Verify plugin enabled
jq '.enabledPlugins' .claude/settings.local.json

# Verify hooks.json exists
cat .claude/plugins/serena-workflow-engine/hooks/hooks.json | jq '.hooks | keys'
```
