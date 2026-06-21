#!/bin/bash
# Wrapper script for starting Serena MCP server with configurable memory paths.
# Reads paths from .serena/memory-paths.conf (one per line) if it exists,
# otherwise falls back to ./.serena/memories.
# Always appends plugin bundled memories from the INSTALLED plugin root.

CONF_FILE=".serena/memory-paths.conf"
DEFAULT_PATH="./.serena/memories"

# Resolve the AUTHORITATIVE installed plugin root from installed_plugins.json,
# NOT the launch-time $PLUGIN_ROOT. After an in-place plugin update, a server
# launched under the old versioned cache dir would otherwise keep serving that
# version's bundled memories (stale `memories:ro`). Resolving the install path
# makes the bundled memories follow the update without restarting the client.
# Falls back to $PLUGIN_ROOT (dev checkouts / missing manifest).
INSTALLED_ROOT=$(python3 - "$PLUGIN_ROOT" <<'PY'
import json, os, sys
fallback = sys.argv[1] if len(sys.argv) > 1 else ''
manifest = os.path.join(os.path.expanduser('~'), '.claude', 'plugins', 'installed_plugins.json')
root = ''
try:
    with open(manifest) as f:
        data = json.load(f)
    entries = (data.get('plugins') or {}).get('swe@EarthmanWeb') or []
    chosen = next((e for e in entries if e.get('scope') == 'user' and e.get('installPath')), None) \
        or next((e for e in entries if e.get('installPath')), None)
    if chosen:
        root = chosen.get('installPath', '')
except Exception:
    root = ''
if not root or not os.path.isdir(root):
    root = fallback
print(root)
PY
)
# Final guard: if resolution produced nothing usable, use launch-time root.
if [ -z "$INSTALLED_ROOT" ] || [ ! -d "$INSTALLED_ROOT" ]; then
  INSTALLED_ROOT="$PLUGIN_ROOT"
fi

if [ -f "$CONF_FILE" ]; then
  # Read non-empty, non-comment lines and join with commas
  PATHS=$(grep -v '^\s*#' "$CONF_FILE" | grep -v '^\s*$' | tr '\n' ',' | sed 's/,$//')
else
  PATHS="$DEFAULT_PATH"
fi

# Append plugin bundled memories from the INSTALLED root (follows updates).
if [ -n "$INSTALLED_ROOT" ]; then
  PATHS="$PATHS,$INSTALLED_ROOT/memories:ro "
fi

PATCH_SCRIPT="$INSTALLED_ROOT/scripts/serena_memory_patch.py"

if [ -f "$PATCH_SCRIPT" ]; then
  # Use patched wrapper for automatic memory prefix resolution
  exec uv run \
    --with "git+https://github.com/EarthmanWeb/serena@swe" \
    python "$PATCH_SCRIPT" \
    --context claude-code \
    --project ./ \
    --enable-web-dashboard=false \
    --memory-path="$PATHS"
else
  # Fallback to direct Serena startup
  exec uvx \
    --from "git+https://github.com/EarthmanWeb/serena@swe" \
    serena start-mcp-server \
    --context claude-code \
    --project ./ \
    --enable-web-dashboard=false \
    --memory-path="$PATHS"
fi
