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
        "--reinstall",
        "--from",
        "git+https://github.com/EarthmanWeb/serena@swe",
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
uvx --from "git+https://github.com/EarthmanWeb/serena@swe" python -c "from serena import __version__; print(__version__)"
```

## Version Sources

The version is defined in two places that must stay in sync:

- `pyproject.toml` → `version = "x.y.z"` (build metadata)
- `src/serena/__init__.py` → `__version__ = "x.y.z"` (runtime version)

## Stale Cache

If `uvx` reports an old version despite the fork being updated:

```bash
# 1. Remove ALL relevant uv caches (environments alone is not enough)
rm -rf ~/.cache/uv/environments-v2/
rm -rf ~/.cache/uv/git-v0/
rm -rf ~/.cache/uv/builds-v0/

# 2. Clear the Claude plugin cache
rm -rf ~/.claude/plugins/cache/EarthmanWeb/

# 3. Reinstall the plugin
claude plugin install swe@EarthmanWeb --scope local


#4. CONFIRM VERSION: 
uvx --from "git+https://github.com/EarthmanWeb/serena@swe" python -c "from serena import __version__; print(__version__)"

#THEN:  Restart the mcp server (if not automatically restarted by the plugin install)

claude /mcp
## find the plugin:swe:serena server and reconnect it

# 5. Restart Claude Code
```

**Why all 3 uv directories?**

- `git-v0/` — cached git clone of the fork (won't pull new commits if stale)
- `builds-v0/` — cached wheel built from the old clone
- `environments-v2/` — installed environment using the old wheel

Clearing only `environments-v2` still uses the stale git clone and build artifacts.
