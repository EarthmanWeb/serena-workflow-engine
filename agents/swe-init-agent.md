---
name: swe-init-agent
description: Autonomous SWE plugin initialization with verification
capabilities:
  - environment_detection
  - mcp_verification
  - lsp_verification
  - plugin_verification
---

# SWE Init Agent

Autonomous agent for initializing the SWE plugin. Completes all setup tasks and verifies success.

## Capabilities

1. **Environment Detection** - Check project state, git, resolve plugin root
2. **Prerequisite Check** - Run bootstrap if project not yet bootstrapped
3. **MCP Verification** - Test Serena and swe-wm MCP servers respond
4. **Serena Onboarding** - Run one-time Serena setup
5. **LSP Verification** - Verify and install language servers
6. **Plugin Verification** - Verify SWE plugin is enabled
7. **CLAUDE.md Review** - Remove conflicting workflow commands
8. **VSCode Extension** - Install Serena Log Viewer
9. **Finalization** - Mark setup complete

## Agent Spawn

```javascript
Task({
  subagent_type: "general-purpose",
  description: "SWE plugin initialization",
  prompt: `[See TASKS section below]`,
});
```

## TASKS

Execute ALL tasks (1-10) in order, then run verifications.

### Task 1: Detect Environment and Resolve Plugin Root

Report:

- Project root (cwd)
- Git repo status
- Existing `.serena/` directory
- Existing `.claude/` directory

**Resolve SWE_PLUGIN_ROOT** — the plugin source may be in different locations depending on how it was installed. Check these paths in order and use the first one found:

```bash
# Resolve SWE plugin root (check in priority order)
SWE_PLUGIN_ROOT=""
CANDIDATES=(
  ".claude/plugins/serena-workflow-engine"                    # Local dev (git submodule)
  "$HOME/.claude/plugins/marketplaces/EarthmanWeb"            # Marketplace install
)

# Also check versioned cache dirs (use latest version)
CACHE_BASE="$HOME/.claude/plugins/cache/EarthmanWeb/swe"
if [ -d "$CACHE_BASE" ]; then
  LATEST_CACHE=$(ls -1d "$CACHE_BASE"/*/ 2>/dev/null | sort -V | tail -1)
  [ -n "$LATEST_CACHE" ] && CANDIDATES+=("${LATEST_CACHE%/}")
fi

for candidate in "${CANDIDATES[@]}"; do
  if [ -f "$candidate/.claude-plugin/plugin.json" ]; then
    SWE_PLUGIN_ROOT="$candidate"
    break
  fi
done

if [ -z "$SWE_PLUGIN_ROOT" ]; then
  echo "ERROR: Could not find SWE plugin installation"
  exit 1
fi

echo "SWE Plugin Root: $SWE_PLUGIN_ROOT"
echo "Version: $(jq -r '.version' "$SWE_PLUGIN_ROOT/.claude-plugin/plugin.json")"
```

**IMPORTANT:** Use `$SWE_PLUGIN_ROOT` in ALL subsequent tasks instead of hardcoded paths. Store it for the session.

### Task 2: Check Prerequisites and Bootstrap

**Requires `$SWE_PLUGIN_ROOT` from Task 1.** Check if the project has been bootstrapped. If not, run the bootstrap script.

```bash
SETUP_FILE=".serena/swe-setup-complete.json"

if [ -f "$SETUP_FILE" ]; then
  BOOTSTRAPPED=$(jq -r '.bootstrapped // false' "$SETUP_FILE")
  COMPLETE=$(jq -r '.complete // false' "$SETUP_FILE")
  if [ "$COMPLETE" = "true" ]; then
    echo "✅ Already fully initialized"
  elif [ "$BOOTSTRAPPED" = "true" ]; then
    echo "✅ Already bootstrapped - continuing with full init"
  else
    echo "⚠️ Setup file exists but not bootstrapped - running bootstrap"
  fi
else
  echo "⚠️ No setup file - running bootstrap"
fi
```

**If not bootstrapped or not complete**, run:

```bash
python3 "$SWE_PLUGIN_ROOT/scripts/swe-bootstrap.py"
```

Bootstrap handles:
- Directory creation (`.serena/`, `.serena/swe/`, `.serena/swe-state/`)
- Language detection → `project.yml`
- `memory-paths.conf` creation/update
- Template memory copying (`_INDEX.md`, `FEATURE_TESTS.md`, `FEATURE_DEV_STANDARDS.md`, `FEATURE_AGENTS.md`)
- `.gitignore` updates
- `swe-setup-complete.json` creation with `bootstrapped: true`

**If bootstrap fails**, report the error and stop.

### Task 3: Verify MCP Servers

Test that the SWE plugin's MCP servers respond:

- `mcp__plugin_swe_serena__list_memories` (Serena memory server)
- `mcp__plugin_swe_swe-wm__swe_wm_read` (Working Memory MCP server)

If any fail, report which ones and stop — these are required for the plugin to function.

### Task 4: Serena Onboarding

```javascript
const status = await mcp__plugin_swe_serena__check_onboarding_performed();
if (!status.performed) {
  await mcp__plugin_swe_serena__onboarding();
}
```

### Task 5: Verify and Install Language Servers

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
  ruby      "gem install ruby-lsp"  # overridden below if rbenv detected
  markdown  "brew install marksman"
  php       "npm install -g intelephense"
  typescript "npm install -g typescript-language-server typescript"
  bash      "npm install -g bash-language-server"
  python    "pipx install python-lsp-server"
  yaml      "npm install -g yaml-language-server"
)

# rbenv awareness: ruby-lsp MUST be installed under the rbenv-managed Ruby,
# not the system/Homebrew Ruby. Serena detects .ruby-version + rbenv and uses
# `rbenv exec` to launch ruby-lsp, so the gem must exist in that Ruby version.
if whence rbenv > /dev/null 2>&1 && [ -f ".ruby-version" ]; then
  LSP_INSTALL[ruby]="rbenv exec gem install ruby-lsp"
  LSP_COMMANDS[ruby]="ruby-lsp"  # check via rbenv shim
fi

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

### Task 6: Verify SWE Plugin is Enabled

**SWE hooks load directly from the plugin folder — no copying needed.**

The plugin's `hooks/hooks.json` uses `${CLAUDE_PLUGIN_ROOT}` which is automatically resolved by Claude Code's plugin system.

```bash
SETTINGS_LOCAL=".claude/settings.local.json"

# Create settings.local.json if missing
[ ! -f "$SETTINGS_LOCAL" ] && echo '{}' > "$SETTINGS_LOCAL"

# Ensure plugin is enabled in settings.local.json
if ! jq -e '.enabledPlugins["swe@EarthmanWeb"] == true' "$SETTINGS_LOCAL" > /dev/null 2>&1; then
  jq '.enabledPlugins["swe@EarthmanWeb"] = true' "$SETTINGS_LOCAL" > "${SETTINGS_LOCAL}.tmp" && mv "${SETTINGS_LOCAL}.tmp" "$SETTINGS_LOCAL"
  echo "Enabled SWE plugin"
else
  echo "SWE plugin already enabled"
fi

# Verify hooks.json exists in plugin
if [ -f "$SWE_PLUGIN_ROOT/hooks/hooks.json" ]; then
  echo "Plugin hooks.json found - hooks will load automatically"
  jq '.hooks | keys' $SWE_PLUGIN_ROOT/hooks/hooks.json
else
  echo "ERROR: Plugin hooks.json missing!"
  exit 1
fi
```

### Task 7: Review CLAUDE.md for Conflicting Workflow Commands

**Check CLAUDE.md for any workflow/session start instructions that conflict with SWE.**

Read CLAUDE.md and look for:

- References to `WF_START`, `WF_INIT`, or workflow initialization
- Instructions to read workflow memories on startup
- Session start procedures that duplicate SWE hooks

If found, remove them — SWE hooks handle workflow initialization automatically.

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

### Task 8: Install Serena Log Viewer VSCode Extension

**Install the VSCode extension that surfaces Serena logs in the Output panel.**

```bash
# Resolve absolute path (symlinks must use absolute paths to work from ~/.vscode/extensions/)
EXT_SOURCE="$(cd "$SWE_PLUGIN_ROOT/vscode-ext/serena-log-viewer" 2>/dev/null && pwd)"
EXT_TARGET="$HOME/.vscode/extensions/serena-log-viewer"

if [ -z "$EXT_SOURCE" ]; then
  echo "⚠️ VSCode extension source not found at $SWE_PLUGIN_ROOT/vscode-ext/serena-log-viewer - skipping"
elif [ -L "$EXT_TARGET" ]; then
  # Verify existing symlink points to correct location
  CURRENT=$(readlink "$EXT_TARGET")
  if [ "$CURRENT" = "$EXT_SOURCE" ]; then
    echo "✅ Serena Log Viewer already installed (symlink correct)"
  else
    rm "$EXT_TARGET"
    ln -s "$EXT_SOURCE" "$EXT_TARGET"
    echo "✅ Serena Log Viewer symlink updated to $EXT_SOURCE"
  fi
elif [ -d "$EXT_TARGET" ]; then
  echo "✅ Serena Log Viewer already installed (directory exists)"
else
  ln -s "$EXT_SOURCE" "$EXT_TARGET"
  echo "✅ Installed Serena Log Viewer VSCode extension"
  echo "   Reload VSCode to activate (Cmd+Shift+P > Reload Window)"
fi
```

This creates a symlink from `~/.vscode/extensions/serena-log-viewer` to the extension source in the plugin directory. The extension tails `~/.serena/logs/<date>/mcp_*.txt` and displays them in the VSCode Output panel under "SWE: Serena Logs".

### Task 9: Auto-Memory Symlink

Run `/swe-sym-link` to set up the auto-memory symlink. This command handles:

- Migrating existing auto-memory files to `.serena/memory/`
- Creating the symlink from `~/.claude/projects/<encoded>/memory` to `.serena/memory/`
- Updating `memory-paths.conf`
- Adding CLAUDE.md directives

See [commands/swe-sym-link.md](../commands/swe-sym-link.md) for full steps.

### Task 10: Finalize Setup

Mark setup as complete. Only run after all previous tasks pass.

```bash
PLUGIN_VERSION=$(jq -r '.version' "$SWE_PLUGIN_ROOT/.claude-plugin/plugin.json")

cat > .serena/swe-setup-complete.json << EOF
{
  "complete": true,
  "timestamp": "$(date -Iseconds)",
  "version": "${PLUGIN_VERSION}",
  "verified": true
}
EOF

echo "✅ Setup complete (version $PLUGIN_VERSION)"
```

## VERIFICATION

After all tasks, verify these 7 conditions:

1. **MCP Servers**: Serena and swe-wm respond
2. **SWE Plugin Enabled**: Plugin is active
   ```bash
   jq '.enabledPlugins["swe@EarthmanWeb"]' .claude/settings.local.json
   # Expected: true
   ```
3. **Plugin Hooks Exist**: hooks.json in plugin folder
   ```bash
   jq '.hooks | keys' $SWE_PLUGIN_ROOT/hooks/hooks.json
   # Expected: ["PostToolUse", "PreToolUse", "SessionStart", "Stop", "UserPromptSubmit"]
   ```
4. **Template Memories Installed**: Template files exist in `.serena/swe/`
   ```bash
   ls .serena/swe/_INDEX.md .serena/swe/feature/FEATURE_TESTS.md .serena/swe/feature/FEATURE_DEV_STANDARDS.md .serena/swe/feature/FEATURE_AGENTS.md
   ```
5. **Serena Onboarding**: Complete
6. **Log Viewer Extension**: Symlink exists at `~/.vscode/extensions/serena-log-viewer`
   ```bash
   [ -L "$HOME/.vscode/extensions/serena-log-viewer" ] || [ -d "$HOME/.vscode/extensions/serena-log-viewer" ] && echo "✅ Log Viewer installed" || echo "⚠️ Log Viewer not installed"
   ```
7. **Auto-Memory Symlink**: Symlink redirects to `.serena/memory/`
   ```bash
   ENCODED_PATH=$(echo "$(pwd)" | sed 's|[/_]|-|g')
   AUTO_MEMORY_DIR="$HOME/.claude/projects/$ENCODED_PATH/memory"
   # Fall back to underscore-preserving encoding if needed
   if [ ! -e "$AUTO_MEMORY_DIR" ]; then
     ALT=$(echo "$(pwd)" | sed 's|/|-|g')
     [ -e "$HOME/.claude/projects/$ALT/memory" ] && AUTO_MEMORY_DIR="$HOME/.claude/projects/$ALT/memory"
   fi
   if [ -L "$AUTO_MEMORY_DIR" ] && [ "$(readlink "$AUTO_MEMORY_DIR")" = "$(pwd)/.serena/memory" ]; then
     echo "✅ Auto-memory symlink correct"
   else
     echo "⚠️ Auto-memory symlink not configured"
   fi
   ```

## COMPLETION

Output summary after all verifications pass:

```
**SETUP COMPLETE**

- MCP Servers: serena, swe-wm
- Serena Onboarding: Complete
- SWE Plugin: Enabled (hooks load from plugin folder)
- Template Memories: Installed to .serena/swe/
- Auto-Memory Symlink: Configured
- Log Viewer: VSCode extension installed

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

### Ruby LSP Returns Empty Symbols `{}`

**Cause:** `ruby-lsp` is installed under the system/Homebrew Ruby but NOT under the rbenv-managed Ruby. Serena detects `.ruby-version` + rbenv and uses `rbenv exec` to launch `ruby-lsp`. If the gem doesn't exist in that Ruby version, the Ruby LS silently fails to start and all `.rb` files fall back to a non-Ruby LS that returns `{}`.

**Diagnosis:**
```bash
# Check which Ruby rbenv uses
rbenv version
# Check if ruby-lsp is installed there
rbenv exec gem list ruby-lsp
# Compare with system gem
/opt/homebrew/bin/gem list ruby-lsp
```

**Fix:**
```bash
rbenv exec gem install ruby-lsp
# Then restart Serena MCP server
```

### Ruby LSP Fails With Native Extension Build Errors

**Cause:** `ruby-lsp` creates a "composed bundle" that includes ALL project gems from `Gemfile`. If any gem requires native extensions with missing system libraries (e.g. `mysql2` needs `libmysqlclient`), the bundle install fails and the Ruby LS never starts.

**Fix options (in order of preference):**

1. **Serena handles this automatically** — pre-creates `.ruby-lsp/bundle_is_composed` marker so ruby-lsp skips the composed bundle install entirely.

2. **Manual marker creation:**
```bash
mkdir -p .ruby-lsp && touch .ruby-lsp/bundle_is_composed
# Then restart Serena MCP server
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
cat $SWE_PLUGIN_ROOT/hooks/hooks.json | jq '.hooks | keys'
```
