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

# ALWAYS-LATEST, WITHOUT RE-RESOLVING EVERY LAUNCH (mcp-wp-cli-terminus pattern):
# Passing the branch spec to uv makes every session start re-resolve the ref and,
# on a moved branch, cold-build inside the MCP connect window (startup timeout).
# Instead resolve REF -> immutable commit SHA with one cheap `git ls-remote` and
# pin the git spec to that SHA:
#   • REF unchanged -> uv reuses its per-SHA cache -> fast launch.
#   • REF moved     -> new SHA -> uv installs the new build automatically
#     (one cold install, covered by MCP_TIMEOUT=300000 in ~/.claude.json).
# Config knobs (env):
#   SWE_SERENA_REF          git ref to run (branch/tag/sha). Default: swe.
#   SWE_SERENA_NO_REFRESH=1 skip the ls-remote re-check; pin the spec to REF
#                           literally (offline / don't re-resolve each start).
SERENA_REPO="github.com/EarthmanWeb/serena"
SERENA_REF="${SWE_SERENA_REF:-swe}"
PIN="$SERENA_REF"
if [ -z "${SWE_SERENA_NO_REFRESH:-}" ]; then
  SHA="$(git ls-remote "https://${SERENA_REPO}.git" "$SERENA_REF" | cut -f1)"
  if [ -z "$SHA" ]; then
    echo "start-serena: could not resolve ref '${SERENA_REF}' in ${SERENA_REPO} (offline? set SWE_SERENA_NO_REFRESH=1 to pin the ref literally)." >&2
    exit 1
  fi
  PIN="$SHA"
fi
SERENA_SPEC="git+https://${SERENA_REPO}@${PIN}"

if [ -f "$PATCH_SCRIPT" ]; then
  # Use patched wrapper for automatic memory prefix resolution
  exec uv run \
    --with "$SERENA_SPEC" \
    python "$PATCH_SCRIPT" \
    --context claude-code \
    --project ./ \
    --enable-web-dashboard=false \
    --memory-path="$PATHS"
else
  # Fallback to direct Serena startup
  exec uvx \
    --from "$SERENA_SPEC" \
    serena start-mcp-server \
    --context claude-code \
    --project ./ \
    --enable-web-dashboard=false \
    --memory-path="$PATHS"
fi
