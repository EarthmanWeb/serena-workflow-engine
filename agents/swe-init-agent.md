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
2. **Auto-Memory Symlink** - Redirect Claude Code auto-memory into `.serena/memory/` **first**, so every memory written during the rest of init lands in the right place
3. **Prerequisite Check** - Run bootstrap if project not yet bootstrapped
3.5. **Serena Reconnect Gate** - After bootstrap writes `memory-paths.conf`, STOP and have the user reconnect Serena so it reads the new memory path before any memory is written (two-pass flow)
4. **MCP Verification** - Test Serena and swe-wm MCP servers respond
5. **Serena Onboarding** - Run one-time Serena setup + migrate default memories into SWE templates
6. **Memory Maintenance** - Relocate Serena's `memory_maintenance` memory into the typed `ref/` folder + link it from MEMORY.md
7. **LSP Verification** - Verify and install language servers
8. **Plugin Verification** - Verify SWE plugin is enabled
9. **CLAUDE.md Review** - Remove conflicting workflow commands
10. **VSCode Extension** - Install Serena Log Viewer
11. **Finalization** - Mark setup complete

## Agent Spawn

```javascript
Task({
  subagent_type: "general-purpose",
  description: "SWE plugin initialization",
  prompt: `[See TASKS section below]`,
});
```

## TASKS

Execute the tasks in order, then run verifications. **This is a two-pass flow gated at Task 3.5:** Pass 1 runs Tasks 1–3 and STOPS at the Task 3.5 reconnect gate; Pass 2 (after the user reconnects Serena and re-runs `/swe-init`) skips Tasks 2–3.5 and runs Tasks 4–11. See Task 3.5 for the gate and resume-detection details.

> **Ordering note:** The auto-memory symlink (Task 2) runs **before** bootstrap and Serena onboarding. This is deliberate — once the symlink is in place, every memory written during the rest of init (bootstrap templates, Serena onboarding defaults, `memory_maintenance`, anything Claude Code auto-writes) lands in the project's `.serena/memory/` instead of the orphaned real auto-memory directory. Do not reorder it later in the sequence.

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

### Task 2: Auto-Memory Symlink (FIRST — before any memory is written)

Run `/swe-symlink-memory` **now**, before bootstrap or onboarding. Establishing the symlink first guarantees that every memory written during the remaining init tasks lands in the project's `.serena/memory/` — not in the orphaned real auto-memory directory. If this ran last (as it used to), memories created by bootstrap templates and Serena onboarding would be written to the un-symlinked directory and lost.

`/swe-symlink-memory` is self-contained and safe to run this early:

- Step 2 does `mkdir -p "$SERENA_MEMORY_DIR"`, so the target exists even before bootstrap creates it.
- Step 3 migrates and reorganizes any pre-existing flat auto-memory files into typed subdirectories:
  - `feedback_*.md` → `feedback/FEEDBACK_*.md`
  - `user_*.md` → `user/USER_*.md`
  - `project_*.md` → `project/PROJECT_*.md`
  - `reference_*.md` → `ref/REF_*.md`
  - `SPEC_*.md` → `spec/SPEC_*.md`
- Step 4 creates the symlink `~/.claude/projects/<encoded>/memory` → `.serena/memory/`.
- Step 5 appends `./.serena/memory` to `memory-paths.conf` if present; if `memory-paths.conf` does not exist yet (bootstrap creates it in Task 3), it prints a non-fatal warning — that is expected at this stage and bootstrap will create the file next.

See [commands/swe-symlink-memory.md](../commands/swe-symlink-memory.md) for full steps.

### Task 3: Check Prerequisites and Bootstrap

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
- Directory creation (`.serena/`, `.serena/memory/`, `.serena/swe-state/`)
- Language detection → `project.yml`
- `memory-paths.conf` creation/update
- Template rendering and installation (`MEMORY.md`, `FEEDBACK_RESPONSE_FORMAT.md`, `FEEDBACK_READ_DOCS_MEANS_LIST.md`, `REF_MCP_BROWSER_DEVTOOLS.md`, `FEATURE_TESTS.md`, `FEATURE_DEV_STANDARDS.md`, `FEATURE_AGENTS.md`) — placeholders like `{{project_name}}`, `{{primary_language}}`, `{{test_framework}}` are auto-filled from detected project info
- `.gitignore` updates
- `.mcp.json` creation/merge (adds `browser-devtools` MCP server via `@ironbee-ai/devtools`)
- `swe-setup-complete.json` creation with `bootstrapped: true`

**If bootstrap fails**, report the error and stop.

> `memory-paths.conf` is written with the single authoritative path `./.serena/memory` (the typed-memory tree the auto-memory symlink targets). It does **not** list `./.serena/memories` — that is the gitignored session-WM directory, not a Serena memory source. After this file is written, Serena must reconnect before any memory is written (see **Task 3.5**).

**After bootstrap succeeds**, verify templates were filled out (not left with raw `{{placeholders}}`):

```bash
# Check for unfilled placeholders in rendered templates
grep -r '{{' .serena/memory/MEMORY.md .serena/memory/feature/FEATURE_*.md 2>/dev/null
```

If any `{{variable}}` placeholders remain, they couldn't be auto-detected. Fill them manually:

1. Read each file with remaining placeholders
2. Determine the correct value from the project context
3. Replace the placeholder with the actual value
4. Report which values were filled manually vs auto-detected

### Task 3.5: Reconnect Serena MCP (MANDATORY GATE — end the turn here)

**Why this gate exists:** The Serena MCP server reads `.serena/memory-paths.conf` **once, at connection time**. When this session started, that file did not exist yet — bootstrap (Task 3) creates it. So the Serena server that is currently connected is still resolving memories against its **default single path**, NOT the `./.serena/memory` path just written to `memory-paths.conf`. If init continues now, every memory operation in Tasks 5, 5b, and 6 (onboarding defaults, template migrations, `memory_maintenance`) resolves against the wrong tree — the split-brain where writes land in one directory while reads see another.

**A subagent cannot reconnect the parent session's MCP servers, and this cannot be automated from within the run.** The reconnect is a user action. Therefore:

1. **STOP init here.** Do NOT proceed to Task 4. Do NOT write any memory yet.
2. Report to the user that bootstrap is complete and `memory-paths.conf` now contains `./.serena/memory`, but Serena must reconnect to pick it up.
3. Instruct the user to reconnect the Serena MCP server:
   - Run `/mcp` → select the `serena` server → **Reconnect** (or restart the session).
4. Tell the user to **resume init by re-running `/swe-init`** once Serena has reconnected. This is safe and idempotent: bootstrap guards on `bootstrapped: true` (Task 3) and skips straight to this point, so the resume picks up at Task 4 with Serena now reading the correct memory paths.

**End the turn here.** Everything below (Task 4 onward) runs on the *resume* invocation, after the reconnect.

> Resume detection: if `swe-setup-complete.json` shows `bootstrapped: true` and `complete: false`, you are on the resume pass — Serena has been reconnected. Skip Tasks 2–3.5 and continue from Task 4. **Before writing any memory on resume, re-verify the Task 2 auto-memory symlink is intact** (it may have failed silently on Pass 1) — re-run `/swe-symlink-memory` if the symlink at `~/.claude/projects/<encoded>/memory` does not resolve to `$(pwd)/.serena/memory`. This is idempotent and guarantees resume-pass memory writes still land in the project tree.

### Task 4: Verify MCP Servers

Test that the SWE plugin's MCP servers respond:

- `mcp__plugin_swe_serena__list_memories` (Serena memory server)
- `mcp__plugin_swe_swe-wm__swe_wm_read` (Working Memory MCP server)

If any fail, report which ones and stop — these are required for the plugin to function.

**WordPress projects only — wp-cli MCP config:** If the project is a WordPress project with a `.devcontainer/` directory, the bootstrap (Task 3) auto-creates `.serena/wp-cli.conf`. Confirm it exists and that `LOCAL_CONTAINER`/`LOCAL_PATH` point at the real container/path (run `docker ps` to confirm the container name). If `REMOTE_SSH` was left as a placeholder (`user@host.example.com`), note that the user must fill in real production SSH details before `target="production"` works. The `wp-cli` MCP server itself is optional — a missing/placeholder config does not block init.

### Task 5: Serena Onboarding

```javascript
const status = await mcp__plugin_swe_serena__check_onboarding_performed();
if (!status.performed) {
  await mcp__plugin_swe_serena__onboarding();
}
```

### Task 5b: Migrate Serena Default Memories Into SWE Templates

Serena's onboarding (Task 5) creates four memories in its own naming convention:
- `project/project_overview`
- `style/style_conventions`
- `suggested/suggested_commands`
- `task/task_completion`

These contain valuable project-specific knowledge discovered during onboarding (tech stack, conventions, commands, verification steps). However, our SWE bootstrap templates already provide the structural framework for this information. This step migrates the discovered content into our templates, then removes the Serena defaults.

**Step 1: Read all four Serena default memories** (skip any that don't exist):

```javascript
const defaults = [
  'project/project_overview',
  'style/style_conventions',
  'suggested/suggested_commands',
  'task/task_completion'
];
for (const name of defaults) {
  await mcp__plugin_swe_serena__read_memory({ memory_name: name });
}
```

**Step 2: Merge discovered knowledge into SWE templates.**

Read each SWE template memory, then update it with the content from the Serena defaults:

| Serena Default | Merge Into | What to Merge |
|---|---|---|
| `project/project_overview` | `feature/FEATURE_DEV_STANDARDS` | Add a `## Project Overview` section at the top with: project purpose, tech stack, architecture summary, entry points, class/file naming conventions |
| `style/style_conventions` | `feature/FEATURE_DEV_STANDARDS` | Populate the language-specific sections (replace generic "follow existing conventions" advice with the actual discovered conventions per language) |
| `suggested/suggested_commands` | `feature/FEATURE_DEV_STANDARDS` | Add a `## Commands` section with: build commands, lint commands, package management commands, git branch info |
| `task/task_completion` | `feature/FEATURE_TESTS` | Add a `## Task Completion Checklist` section with the project-specific verification steps (lint, build, test commands) |

Use `mcp__plugin_swe_serena__edit_memory` to update each target memory. Preserve all existing template structure — add new sections, don't overwrite existing ones.

**Step 3: Delete the Serena default memories and their empty folders.**

```javascript
const toDelete = [
  'project/project_overview',
  'style/style_conventions',
  'suggested/suggested_commands',
  'task/task_completion'
];
for (const name of toDelete) {
  await mcp__plugin_swe_serena__delete_memory({ memory_name: name });
}
```

Then remove the now-empty topic folders from the Serena memories directory:

```bash
SERENA_MEMORIES_DIR=".serena/memories"
for dir in project style suggested task; do
  if [ -d "$SERENA_MEMORIES_DIR/$dir" ]; then
    rmdir "$SERENA_MEMORIES_DIR/$dir" 2>/dev/null && echo "Removed empty folder: $SERENA_MEMORIES_DIR/$dir" || echo "Folder not empty, skipping: $SERENA_MEMORIES_DIR/$dir"
  fi
done
```

**Note:** Uses `rmdir` (not `rm -rf`) so only truly empty folders are removed. If a folder has other files, it's left intact.

### Task 6: Copy the Memory Maintenance Memory Into the Local Memory System

Serena ships a built-in **memory-maintenance** guide (`memory_maintenance`) describing the discovery model, memory style, add/update threshold, and maintenance actions. It is NOT reliably materialized as a project-local file: `ensure_memory_maintenance_memory()` returns `global/memory_maintenance` **without creating a project copy** when a global copy exists, and even when it does seed a project copy, that copy is flat and un-indexed. This task **copies the guide's content into this project's local memory system** as a typed `ref/REF_MEMORY_MAINTENANCE` memory and **links it from MEMORY.md** — so it is committed with the repo and discoverable, regardless of Serena's global/project precedence.

Never overwrite an existing copy: if `.serena/memory/ref/REF_MEMORY_MAINTENANCE.md` already exists, skip the write (Steps 1–2) but STILL ensure the MEMORY.md link (Step 3).

**Step 1: Obtain the memory-maintenance content.**

Prefer the shipped Serena resource so the copy is deterministic. Fall back to whatever Serena seeded during onboarding (Task 5) if the resource path is not resolvable:

```bash
# Serena package resource (canonical source of the guide)
RES="$(python3 -c "import serena, os; print(os.path.join(os.path.dirname(serena.__file__), 'resources', 'memory_maintenance.md'))" 2>/dev/null)"
if [ -n "$RES" ] && [ -f "$RES" ]; then
  echo "Source: shipped resource $RES"
  cat "$RES"
else
  # Fallback: the copy Serena's onboarding (Task 5) may have seeded into the project memory dir
  echo "Resource not resolvable — falling back to project-seeded memory_maintenance (if any)"
  cat .serena/memory/memory_maintenance.md 2>/dev/null || echo "(none found — read the 'memory_maintenance' Serena memory instead)"
fi
```

If neither source yields content, read Serena's memory directly and use that text:

```javascript
const maint = await mcp__plugin_swe_serena__read_memory({ memory_name: "memory_maintenance" });
```

**Step 2: Write it into the local memory system as `ref/REF_MEMORY_MAINTENANCE` (sanctioned tool).**

Use the Serena memory tool — NOT a raw file move — so the memory is registered in the project's memory system. Prepend the standard SWE front-matter, then the guide content from Step 1 (strip any Serena front-matter it already carried so there is exactly one block):

```javascript
await mcp__plugin_swe_serena__write_memory({
  memory_name: "ref/REF_MEMORY_MAINTENANCE",
  content: `---
name: Memory Maintenance
description: How memories should be created and maintained in this project — discovery model, style, add/update threshold, maintenance actions
metadata:
  type: reference
---

<contents of the memory_maintenance guide from Step 1, verbatim>`
});
```

If Serena's onboarding seeded a flat `memory_maintenance` memory into `.serena/memory/memory_maintenance.md`, delete it after the typed copy is written so it isn't duplicated:

```bash
[ -f ".serena/memory/ref/REF_MEMORY_MAINTENANCE.md" ] && rm -f ".serena/memory/memory_maintenance.md"
```

**Step 3: Ensure a MEMORY.md index link (required — not optional).**

MEMORY.md MUST link to the memory. Add a one-line entry under the `## Memory Types` (or equivalent) section of `.serena/memory/MEMORY.md`, only if `REF_MEMORY_MAINTENANCE` is not already linked:

```
- [Memory Maintenance](ref/REF_MEMORY_MAINTENANCE.md) — how memories are created & maintained (discovery model, style, add/update threshold, maintenance actions)
```

Verify the link is present before finishing this task:

```bash
grep -q 'REF_MEMORY_MAINTENANCE' .serena/memory/MEMORY.md \
  && echo "✅ MEMORY.md links REF_MEMORY_MAINTENANCE" \
  || echo "❌ MEMORY.md missing REF_MEMORY_MAINTENANCE link — add it"
```

### Task 7: Verify and Install Language Servers

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

### Task 8: Verify SWE Plugin is Enabled

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

### Task 9: Review CLAUDE.md for Conflicting Workflow Commands

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

### Task 10: Install Serena Log Viewer VSCode Extension

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

### Task 11: Finalize Setup

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
4. **Template Memories Rendered**: Template files exist in `.serena/memory/` with placeholders filled
   ```bash
   # Check files exist
   ls .serena/memory/MEMORY.md .serena/memory/feedback/FEEDBACK_RESPONSE_FORMAT.md .serena/memory/feedback/FEEDBACK_READ_DOCS_MEANS_LIST.md .serena/memory/ref/REF_MCP_BROWSER_DEVTOOLS.md .serena/memory/feature/FEATURE_TESTS.md .serena/memory/feature/FEATURE_DEV_STANDARDS.md .serena/memory/feature/FEATURE_AGENTS.md
   # Check no unfilled placeholders remain
   UNFILLED=$(grep -rl '{{' .serena/memory/MEMORY.md .serena/memory/feature/FEATURE_*.md 2>/dev/null)
   if [ -n "$UNFILLED" ]; then
     echo "⚠️ Unfilled placeholders in: $UNFILLED"
   else
     echo "✅ All templates rendered"
   fi
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
- Template Memories: Rendered to .serena/memory/ (placeholders filled)
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
