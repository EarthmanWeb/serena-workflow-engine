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
3. Prompt for additional Serena memory paths (e.g. `./docs:ro`)
4. Inject `CLAUDE_PREFIX.md` into your project's `CLAUDE.md`
5. Create `.serena/.gitignore` for runtime file exclusions
6. Verify MCP servers (Serena, swe-wm)
7. Run Serena onboarding
8. Verify and install language servers
9. Enable the SWE plugin
10. Review CLAUDE.md for conflicts
11. Install the Serena Log Viewer VSCode extension
12. Finalize setup

### 4. Restart Claude Code and onboard your first feature

```
/swe-feature-onboard FEATURE_[KEY]
```

## Directory Structure

```
.serena/
├── .gitignore              # Runtime file exclusions (auto-created)
├── memory-paths.conf       # Serena memory path config
├── project.yml             # Detected languages
├── swe/                    # Feature memories, refs, specs
│   ├── feature/
│   ├── ref/
│   └── ...
├── memories/               # Working Memory files (per-session)
│   └── WM_<session>.md
├── swe-state/              # Decoupled workflow state (authoritative)
│   └── <session>.state
├── streams/                # Append-only event logs
│   ├── <session>.jsonl
│   └── .init_<session>     # Init gate sentinel
├── swe-setup-complete.json # Setup completion flag
└── swe-bypass.json         # SWE disabled flag (if user declines)
```

## Custom Memory Paths

During bootstrap, you'll be prompted to add extra folders for Serena to access.
You can also edit `.serena/memory-paths.conf` manually (one path per line):

```
./.serena/swe
./.serena/memories
./docs:ro
```

Append `:ro` for read-only access. Plugin bundled memories are always appended automatically. See [MCP-README.md](MCP-README.md) for details.

## Commands

| Command | Description |
|---|---|
| `/swe-init` | First-time setup |
| `/swe-status` | Show current state |
| `/swe-feature-onboard [KEY]` | Register existing feature |
| `/swe-feature-update [KEY]` | Update feature memories |
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
| Local memories | `.serena/swe/` | Project-specific feature memories |
| Working memory | `.serena/memories/` | Session-scoped WM files |
| State files | `.serena/swe-state/` | Authoritative workflow state |

See `memories/REF_SWE_DEVELOPMENT.md` for full development standards.
