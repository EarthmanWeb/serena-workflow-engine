# Serena Workflow Engine

21-state workflow engine for Claude Code with RLVR learning, swarm coordination,
and Serena memory persistence.

---

## Installation

### 1. Configure the plugin

Add to `.claude/settings.local.json` (create if it doesn't exist):

```json
{
  "extraKnownMarketplaces": {
    "EarthmanWebSwe": {
      "source": {
        "source": "git",
        "url": "https://github.com/EarthmanWeb/serena-workflow-engine",
        "ref": "main"
      }
    }
  },
  "enabledPlugins": {
    "swe@EarthmanWebSwe": true
  }
}
```

### 2. Verify installation

```bash
claude plugin list
```

Should show: `swe@EarthmanWebSwe` with status `✔ enabled`

### 3. Restart Claude Code

- **CLI**: Start a new `claude` session
- **VSCode**: Reload the window (`Cmd+Shift+P` → "Developer: Reload Window")

### 4. Initialize the plugin

After restart, paste this prompt into Claude Code:

```
Read the file .claude/plugins/serena-workflow-engine/commands/swe-init.md and execute the setup steps it describes. Install any missing MCP servers to ~/.claude.json and complete the 7-step initialization.
```

This will:

- Detect and install required MCPs (serena, claude-flow, ruv-swarm)
- Run Serena onboarding
- Create core memories
- Configure .gitignore

### 5. Start working

After setup, the workflow guides you automatically. Type any task to begin.

---

## Local Development Installation

For contributing to or modifying the plugin itself.

### 1. Clone as submodule

```bash
cd your-project
git submodule add https://github.com/EarthmanWeb/serena-workflow-engine .claude/plugins/serena-workflow-engine
chmod +x .claude/plugins/serena-workflow-engine/hooks/*.py
```

### 2. Configure for local development

Add to `.claude/settings.local.json`:

```json
{
  "extraKnownMarketplaces": {
    "localDev": {
      "source": {
        "source": "directory",
        "path": "./plugins/serena-workflow-engine"
      }
    }
  },
  "enabledPlugins": {
    "swe@localDev": true
  }
}
```

**Note:** Directory path is relative to the `.claude/` folder.

### 3. Alternative: CLI installation

```bash
# Add marketplace (use ABSOLUTE path)
claude plugin marketplace add "$(pwd)/.claude/plugins/serena-workflow-engine"

# Install and enable
claude plugin install swe@localDev --scope local
claude plugin enable swe@localDev --scope local

# Verify
claude plugin list
claude plugin marketplace list
```

### 4. Updating the submodule

```bash
# Pull latest changes
cd .claude/plugins/serena-workflow-engine
git pull origin main

# Or update from parent repo
git submodule update --remote .claude/plugins/serena-workflow-engine
```

### 5. Switching between git and local

To switch from git source to local (or vice versa), update `extraKnownMarketplaces` in settings and restart Claude Code. Only one source can be active at a time per marketplace name.

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
