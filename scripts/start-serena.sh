#!/bin/bash
# Wrapper script for starting Serena MCP server with configurable memory paths.
# Reads paths from .serena/memory-paths.conf (one per line) if it exists,
# otherwise falls back to ./.serena/memories.
# Always appends plugin bundled memories from $PLUGIN_ROOT/memories.

CONF_FILE=".serena/memory-paths.conf"
DEFAULT_PATH="./.serena/memories"

if [ -f "$CONF_FILE" ]; then
  # Read non-empty, non-comment lines and join with commas
  PATHS=$(grep -v '^\s*#' "$CONF_FILE" | grep -v '^\s*$' | tr '\n' ',' | sed 's/,$//')
else
  PATHS="$DEFAULT_PATH"
fi

# Append plugin bundled memories
if [ -n "$PLUGIN_ROOT" ]; then
  PATHS="$PATHS,$PLUGIN_ROOT/memories"
fi

exec uvx --refresh \
  --from "git+https://github.com/EarthmanWeb/serena@swe" \
  serena start-mcp-server \
  --context ide-assistant \
  --project ./ \
  --enable-web-dashboard=false \
  --memory-path="$PATHS"
