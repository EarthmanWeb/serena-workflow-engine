# Serena Workflow Engine

21-state workflow engine for Claude Code with Serena memory persistence, swarm coordination, and RLVR learning.

## Prerequisites

- **Claude Code** installed globally
- **Python 3** (for hook scripts and bootstrap)
- **jq** (for JSON processing in setup scripts)

## Install

### 1. Install the plugin

```bash
claude plugin marketplace add https://github.com/EarthmanWeb/serena-workflow-engine.git
claude plugin install swe@EarthmanWeb --scope local
```

### 2. Enable auto-update

In Claude Code CLI: `claude /plugin` → **Marketplaces** tab → **EarthmanWeb** → **Enable auto-update**

### 3. Restart Claude Code and initialize

```
/swe-init
```

The init agent will:
1. Detect your environment and resolve the plugin root
2. Run bootstrap (creates directories, detects languages, installs templates)
3. Verify MCP servers (Serena, swe-wm)
4. Run Serena onboarding
5. Verify and install language servers
6. Enable the SWE plugin
7. Review CLAUDE.md for conflicts
8. Install the Serena Log Viewer VSCode extension
9. Finalize setup

### 4. Restart Claude Code and onboard your first feature

```
/swe-feature-onboard FEATURE_[KEY]
```

## Custom Memory Paths

Create `.serena/memory-paths.conf` in your project root (one path per line):

```
./.serena/swe
./docs
```

Plugin bundled memories are always appended automatically. See [MCP-README.md](MCP-README.md) for details.

## Commands

| Command | Description |
|---|---|
| `/swe-init` | First-time setup |
| `/swe-status` | Show current state |
| `/swe-feature-onboard [KEY]` | Register existing feature |
| `/swe-scaffold` | Scaffold new project |
| `/swe-reset` | Reset workflow |
| `/swe-goto [STATE]` | Force transition (debug) |
| `/swe-cleanup` | Archive completed work |

## Troubleshooting

### Stale plugin or Serena version

```bash
rm -rf ~/.cache/uv/environments-v2/ ~/.cache/uv/git-v0/ ~/.cache/uv/builds-v0/
rm -rf ~/.claude/plugins/cache/EarthmanWeb/
claude plugin marketplace add https://github.com/EarthmanWeb/serena-workflow-engine
claude plugin install swe@EarthmanWeb --scope local
```

Restart Claude Code.

### Debug

```bash
claude --debug
```

---

## Contributing

### Local dev setup

```bash
git submodule update --init .claude/plugins/serena-workflow-engine
bash .claude/plugins/serena-workflow-engine/scripts/install-hooks.sh
```

### Dual-location architecture

| Location | Path | Purpose |
|---|---|---|
| Plugin folder | `.claude/plugins/serena-workflow-engine/` | Generic/portable code |
| Local memories | `.serena/swe/` | Project-specific adaptations |

See `memories/REF_SWE_DEVELOPMENT.md` for full development standards.

