# Serena Workflow Engine

21-state workflow engine for Claude Code with Serena memory persistence, swarm coordination, and RLVR learning.

## Install

### 1. Install MCP servers

```bash
claude mcp add claude-flow -s local -- npx claude-flow@v3alpha mcp start
claude mcp add sequential-thinking -s local -- npx -y @modelcontextprotocol/server-sequential-thinking
claude mcp add playwright -s local -- npx -y @playwright/mcp@latest
claude mcp add ruv-swarm -s local -- npx -y ruv-swarm mcp start
```

### 2. Install marksman (required for markdown symbol extraction)

```bash
brew install marksman
```

### 3. Install the plugin

```bash
claude plugin marketplace add https://github.com/EarthmanWeb/serena-workflow-engine.git
claude plugin install swe@EarthmanWeb --scope local
```

### 4. Enable auto-update

In Claude Code: `/plugin` → **Marketplaces** tab → **EarthmanWeb** → **Enable auto-update**

### 5. Restart Claude Code and initialize

```
/swe-init
```

### 6. Onboard your first feature

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

## License

MIT
