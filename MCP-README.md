# Serena Workflow Engine MCP Plugin

### Custom memory paths

The plugin uses a wrapper script (`scripts/start-serena.sh`) that reads memory paths from a project-local config file. Plugin bundled memories are always appended automatically.

To customize paths, create `.serena/memory-paths.conf` in your project root:

```
# one path per line
./.serena/swe
./docs
```

Do NOT include the plugin cache path — it's appended automatically.

After changing paths, clear the cache and restart:

```bash
rm -rf ~/.claude/plugins/cache/EarthmanWeb/
claude plugin install swe@EarthmanWeb --scope local
```

Then restart Claude Code.

If no `.serena/memory-paths.conf` exists, the default is `./.serena/memories`.

---

# MCP Config Cache Issue

## Problem

Changes to plugin config don't take effect.

## Cause

Claude caches plugin config at: `~/.claude/plugins/cache/EarthmanWeb/swe/<version>/`

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
claude plugin marketplace remove EarthmanWeb
claude plugin marketplace add https://github.com/EarthmanWeb/serena-workflow-engine
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
