# Serena Workflow Engine

21-state workflow engine for Claude Code with RLVR learning, swarm coordination,
and Serena memory persistence.

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


---
# Plugin Installation

Works best with Claude Flow
and the Serena Workflow Engine (SWE) plugin for Claude.

## Install

### 1. Install Claude Flow:

```bash

claude plugin marketplace add https://github.com/EarthmanWeb/claude-flow-plugin.git#plugin

claude plugin install claude-flow@claude-flow-plugin  --scope local
```

### 2. Install SWE (production):

```bash
claude plugin marketplace add https://github.com/EarthmanWeb/serena-workflow-engine.git
claude plugin install swe@EarthmanWeb --scope local
```

### 3. Enable auto-update (recommended)

To receive updates automatically when new versions are released:

1. Run `/plugin` in Claude Code
2. Press **Tab** to go to **Marketplaces** tab
3. Select **EarthmanWeb** from the list
4. Press **Enter**
5. Select **Enable auto-update**

Now you'll get updates automatically on Claude Code startup.

### 4. Verify installation

```bash
claude plugin list
```

Should show:
```
  ❯ claude-flow@claude-flow-plugin
    Version: 2.5.17
    Scope: local
    Status: ✔ enabled

  ❯ swe@EarthmanWeb
    Version: 1.0.23
    Scope: local
    Status: ✔ enabled
```

### 5. Restart Claude Code

- **CLI**: Start a new `claude` session
- **VSCode**: Reload the window (`Cmd+Shift+P` → "Developer: Reload Window")

### 6. Initialize the plugin

After restart, use this command in CLaude Code:

```
/swe-init
```

This will:

- Run Serena onboarding
- Copy plugin memories to `.serena/memories/`
- Create core memories for your codebase
- Configure .gitignore

### 7. Start working

After setup, the workflow guides you automatically. Type any task to begin.

Recommend to start with Onboarding your first feature:

```
/swe-feature-onboard FEATURE_[YOURSHORTNAME] 
```
The onboarding wizard will help you register existing code features for management.

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
   claude plugin enable swe@EarthmanWeb --scope local
   ```

3. **Restart Claude Code:**
   - CLI: Start new session
   - VSCode: Reload window


### Plugin not auto-updating to latest version

If auto-update is enabled but new sessions keep loading a stale version:

```bash
# 1. Remove the cached plugin and marketplace clone
rm -rf ~/.claude/plugins/cache/EarthmanWeb/
rm -rf ~/.claude/plugins/marketplaces/EarthmanWeb/

# 2. Start a new Claude Code session
# Claude Code will re-clone the marketplace and install the latest version
```

This forces a fresh clone from GitHub on next startup. Common causes:
- Marketplace was originally added via local directory instead of git
- Stale clone from a previous source configuration

### Marketplace not loading

```bash
# Verify marketplace is registered
claude plugin marketplace list

# If not listed, add it again - see above
```


### Debug mode

Run Claude with debug output:

```bash
claude --debug
```

Shows plugin loading details, manifest validation errors, and hook registration.

---


# **STOP READING HERE IF YOU ARE NOT CONTRIBUTING TO THE PLUGIN**

---
---

## Local Development Installation

For contributing to or modifying the plugin itself.

### Setup

```bash
git submodule update --init .claude/plugins/serena-workflow-engine
```

### Install Git Hooks

After cloning or initializing the submodule, install the pre-commit hook to auto-bump version numbers on each commit:

```bash
bash .claude/plugins/serena-workflow-engine/scripts/install-hooks.sh
```

This symlinks the pre-commit hook into the submodule's git hooks directory. It must be run once per clone — the symlink is local and not stored in git.

### Update

```bash
git submodule update --remote .claude/plugins/serena-workflow-engine
```

**Recommended scope**: `local` for development plugins (installs into settings.local.json and keeps them out of
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


### Troubleshooting

If you experience issues after changing files in dev, be sure to clear the cache and reinstall:

```bash

rm -rf ~/.claude/plugins/cache/serena-workflow-engine/
rm -rf ~/.claude/plugins/cache/swe/
claude plugin install swe@EarthmanWeb --scope local

```
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


### Development Docs

- `memories/REF_SWE_DEVELOPMENT.md` - Full development standards
- After `/swe-init`: `DOM_SWE_DEVELOPMENT`, `DOM_SWE_HOOKS` in local memories

---
