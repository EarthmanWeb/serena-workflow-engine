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
        ".serena/swe/arch,.serena/swe/dev,.serena/swe/feature",
        "--enable-web-dashboard=false"
      ],
      "env": {}
    }
  }
}
```

---

# MCP Config Cache Issue

## Problem

Changes to `.claude/plugins/serena-workflow-engine/.mcp.json` like adding new folders don't take effect.

## Cause

Claude caches MCP config at: `~/.claude/plugins/cache/EarthmanWeb/swe/<version>/.mcp.json`

## Fix

```bash
rm -rf ~/.claude/plugins/cache/EarthmanWeb/
claude plugin install swe@EarthmanWeb --scope local
```

Then restart Claude Code.

---

# Checking Serena Fork Version

## Quick Check

```bash
uvx --from "git+https://github.com/EarthmanWeb/serena@feature-multiplefoldersupport" python -c "from serena import __version__; print(__version__)"
```

## Version Sources

The version is defined in two places that must stay in sync:

- `pyproject.toml` → `version = "x.y.z"` (build metadata)
- `src/serena/__init__.py` → `__version__ = "x.y.z"` (runtime version)

## Stale Cache

If `uvx` reports an old version despite the fork being updated:

```bash
# Remove stale uv environments
rm -rf ~/.cache/uv/environments-v2/
# Or use --reinstall in .mcp.json args instead of --refresh
```
