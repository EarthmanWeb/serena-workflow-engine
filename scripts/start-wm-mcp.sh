#!/bin/bash
# Start the SWE Working Memory MCP server (stdio JSON-RPC 2.0).
# Uses PLUGIN_ROOT env var set by plugin.json to locate the Python script.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="${PLUGIN_ROOT:-$(dirname "$SCRIPT_DIR")}"

# Set CLAUDE_PROJECT_DIR if not already set (needed by core modules)
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

exec python3 "$PLUGIN_ROOT/hooks/swe_hooks/mcp/wm_server.py"
