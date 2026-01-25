# Serena Workflow Engine

21-state workflow engine for Claude Code with RLVR learning, swarm coordination,
and Serena memory persistence.

---

## Installation

### 1. Add the marketplace and install

```bash
# Add the marketplace (name "swe" comes from marketplace.json)
claude plugin marketplace add https://github.com/EarthmanWeb/serena-workflow-engine.git

# Install and enable the plugin
claude plugin install swe@EarthmanWeb --scope local
claude plugin enable swe@EarthmanWeb --scope local
```

This writes the following to `.claude/settings.local.json`:

```json
{
  "enabledPlugins": {
    "swe@EarthmanWeb": true
  }
}
```

### 2. Enable auto-update (recommended)

To receive updates automatically when new versions are released:

1. Run `/plugin` in Claude Code
2. Press **Tab** to go to **Marketplaces** tab
3. Select **EarthmanWeb** from the list
4. Press **Enter**
5. Select **Enable auto-update**

Now you'll get updates automatically on Claude Code startup.

### 3. Verify installation

```bash
claude plugin list
```

Should show: `swe@EarthmanWeb` with status `✔ enabled`

### 4. Restart Claude Code

- **CLI**: Start a new `claude` session
- **VSCode**: Reload the window (`Cmd+Shift+P` → "Developer: Reload Window")

### 5. Initialize the plugin

After restart, paste this prompt into Claude Code:

```
Read the file .claude/plugins/serena-workflow-engine/commands/swe-init.md and execute the setup steps it describes. Install any missing MCP servers to ~/.claude.json and complete the 7-step initialization.
```

This will:

- Detect and install required MCPs (serena, claude-flow, ruv-swarm)
- Run Serena onboarding
- Create core memories
- Configure .gitignore

### 6. Start working

After setup, the workflow guides you automatically. Type any task to begin.

---

## Local Development Installation

For contributing to or modifying the plugin itself.

### 1. Clone as submodule

```bash
cd your-project
git submodule add https://github.com/EarthmanWeb/serena-workflow-engine.git .claude/plugins/serena-workflow-engine
chmod +x .claude/plugins/serena-workflow-engine/hooks/*.py

# Install git hooks for auto version bumping
.claude/plugins/serena-workflow-engine/scripts/install-hooks.sh
```

### 2. Add the marketplace and install

```bash
# Add marketplace from local directory (name "EarthmanWeb" comes from marketplace.json)
claude plugin marketplace add "$(pwd)/.claude/plugins/serena-workflow-engine"

# Install and enable
claude plugin install swe@EarthmanWeb --scope local
claude plugin enable swe@EarthmanWeb --scope local

# Verify
claude plugin list
claude plugin marketplace list
```

This writes the following to `.claude/settings.local.json`:

```json
{
  "extraKnownMarketplaces": {
    "swe": {
      "source": {
        "source": "directory",
        "path": "./plugins/serena-workflow-engine"
      }
    }
  },
  "enabledPlugins": {
    "swe@EarthmanWeb": true
  }
}
```

**Note:** Directory path is relative to the `.claude/` folder.

### 3. Install git hooks (auto version bump)

The plugin includes git hooks that auto-increment the version on each commit:

```bash
cd .claude/plugins/serena-workflow-engine
./scripts/install-hooks.sh
```

This installs a pre-commit hook that bumps the patch version in `plugin.json` and `marketplace.json` automatically. Combined with marketplace auto-update, users get updates on next Claude Code start.

**Manual version bump** (if hooks not installed):
```bash
./scripts/bump-version.sh
```

### 4. Updating the submodule

```bash
# Pull latest changes
cd .claude/plugins/serena-workflow-engine
git pull origin main

# Or update from parent repo
git submodule update --remote .claude/plugins/serena-workflow-engine
```

### 5. Enable marketplace auto-update (for users)

Users can enable auto-update to receive changes automatically:

1. Run `/plugin` in Claude Code
2. Go to **Marketplaces** tab
3. Select **EarthmanWeb**
4. Choose **Enable auto-update**

Or set environment variable:
```bash
export FORCE_AUTOUPDATE_PLUGINS=true
```

### 6. Switching between git and local

To switch from git source to local (or vice versa), update `extraKnownMarketplaces` in settings and restart Claude Code. Only one source can be active at a time per marketplace name.

---

## Overriding MCP Configuration

You can customize the Serena MCP server configuration by creating a local `.mcp.json` file in the plugin directory. This is useful for:

- Adding custom memory folder paths
- Forcing fresh pulls from the remote repository
- Changing Serena options without modifying the plugin

### Local .mcp.json Override

Create `.claude/plugins/serena-workflow-engine/.mcp.json`:

```json
{
  "mcpServers": {
    "plugin:swe:serena": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--refresh",
        "--from",
        "git+https://github.com/EarthmanWeb/serena@feature-multiplefoldersupport",
        "serena",
        "start-mcp-server",
        "--context",
        "ide-assistant",
        "--project",
        "./",
        "--additional-folders",
        ".serena/memories/arch,.serena/memories/dev,.serena/memories/feature",
        "--enable-web-dashboard=false"
      ],
      "env": {}
    }
  }
}
```

### Key Options

| Option | Purpose |
| ------ | ------- |
| `--refresh` | Force `uvx` to check for latest commits on the remote branch. Without this, the package is cached after first fetch. |
| `--additional-folders` | Comma-separated list of memory folders for Serena to index |
| `--context` | Serena context mode (`ide-assistant`, `cli`, etc.) |
| `--enable-web-dashboard` | Enable/disable Serena's web dashboard |

### Forcing Updates Without --refresh

If you prefer faster startup (no remote check), omit `--refresh` and manually clear the cache when you want updates:

```bash
# Clear all uv cache
uv cache clean

# Or clear just serena
uvx cache clean serena
```

---

## How It Works (CLI + VSCode)

Claude Code CLI and VSCode extension **share the same configuration files**:

| Scope     | Settings File                 | Use Case                                |
| --------- | ----------------------------- | --------------------------------------- |
| `user`    | `~/.claude/settings.json`     | Personal plugins across all projects    |
| `project` | `.claude/settings.json`       | Team plugins shared via version control |
| `local`   | `.claude/settings.local.json` | Project-specific, gitignored            |

When you install a plugin via CLI, it writes to these settings files. The VSCode
extension reads the same files, so plugins are automatically available in both
interfaces.

**Recommended scope**: `local` for development plugins (keeps them out of
version control)

---

## Commands

| Command              | Description                |
| -------------------- | -------------------------- |
| `/swe-init`          | First-time setup           |
| `/swe-status`        | Show current state         |
| `/swe-reset`         | Reset workflow             |
| `/swe-goto [STATE]`  | Force transition           |
| `/swe-memory`        | Manage WORKING_MEMORY      |
| `/swe-scaffold`      | Scaffold new project       |
| `/swe-onboard [KEY]` | Register existing feature  |
| `/swe-onboard-quick` | Quick feature registration |
| `/swe-cleanup`       | Archive completed work     |

---

## Onboarding Features / Scaffolding New Apps

### Scaffolding a New Project

For empty or new projects:

```
/swe-scaffold
```

8-stage wizard: app type → platform config → goals → assets → recommendations →
architecture → memories → analysis.

Creates: `.serena/memories/`, core memories, architecture folders.

### Onboarding an Existing Feature

To register an existing codebase feature:

```
/swe-onboard [KEY]
```

5-stage wizard: identifier → name → folders → dependencies → analysis mode.

Creates: `FEATURE_[KEY]`, updates `INDEX_FEATURES`, optionally `DOM_*` and
`SYS_*` memories.

### Quick Onboarding

Fast registration without wizard:

```
/swe-onboard-quick [KEY] [NAME] [PATH]
```

Example: `/swe-onboard-quick AUTH "Authentication" src/auth/`

---

## Troubleshooting

### Plugin not appearing after installation

1. **Verify installation:**
   ```bash
   claude plugin list
   ```
   Plugin should show `✔ enabled`

2. **If disabled, enable it:**
   ```bash
   claude plugin enable swe@swe --scope local
   ```

3. **Restart Claude Code:**
   - CLI: Start new session
   - VSCode: Reload window

### Marketplace not loading

```bash
# Verify marketplace is registered
claude plugin marketplace list

# If not listed, add it again
claude plugin marketplace add "$(pwd)/.claude/plugins/serena-workflow-engine"
```

### Commands not appearing

1. Verify plugin directory structure has `commands/` at root (not inside
   `.claude-plugin/`)
2. Check that `.md` files exist in `commands/` directory
3. Run with debug: `claude --debug`

### Hook scripts not executing

```bash
# Ensure scripts are executable
chmod +x .claude/plugins/serena-workflow-engine/hooks/*.sh
```

### Debug mode

Run Claude with debug output:

```bash
claude --debug
```

Shows plugin loading details, manifest validation errors, and hook registration.

---

## Requirements

- **Serena MCP** - Memory persistence
- **Claude-Flow MCP** - Swarm orchestration
- **RUV-Swarm MCP** - DAA learning
- **jq** - JSON parsing (`brew install jq`)

---

## Development Standards

SWE uses a **dual-location architecture**. Understanding this is critical for
contributing:

### File Locations

| Location           | Path                                      | Purpose                      |
| ------------------ | ----------------------------------------- | ---------------------------- |
| **Plugin Folder**  | `.claude/plugins/serena-workflow-engine/` | Generic/portable code        |
| **Local Memories** | `.serena/memories/`                       | Project-specific adaptations |

### Change Classification

| Change Type               | Plugin Folder | Local Memories       |
| ------------------------- | ------------- | -------------------- |
| Generic workflow logic    | ✅ YES        | ✅ SYNC (copy after) |
| Generic hook behavior     | ✅ YES        | ❌ No                |
| Project-specific patterns | ❌ No         | ✅ YES               |
| New skill/command         | ✅ YES        | ❌ No                |

### Hook Sync Requirement (CRITICAL)

When modifying hooks, **THREE files must stay synchronized**:

1. **Hook Script:** `hooks/*.py`
2. **hooks.json:** `hooks/hooks.json` (uses `${CLAUDE_PLUGIN_ROOT}`)
3. **settings.json:** `.claude/settings.json` (uses literal paths)

```bash
# Verify hooks match
diff <(jq -S '.hooks' hooks/hooks.json) \
     <(jq -S '.hooks' ../../settings.json | \
       sed 's|\.claude/plugins/serena-workflow-engine|\${CLAUDE_PLUGIN_ROOT}|g')
```

### Development Docs

- `memories/REF_SWE_DEVELOPMENT.md` - Full development standards
- After `/swe-init`: `DOM_SWE_DEVELOPMENT`, `DOM_SWE_HOOKS` in local memories

---

## How It Works

The engine enforces a 21-state workflow:

```
START → CLASSIFY → PLAN → EXECUTE → VERIFY → DONE → CLEANUP
           ↓
       RESEARCH / DEBUG / CLARIFY (as needed)
```

Key features:

- Auto plan mode for medium+ complexity
- Checkpoint every 3 edits
- RLVR learning at task completion
- Swarm agents for large tasks

---

## License

MIT
