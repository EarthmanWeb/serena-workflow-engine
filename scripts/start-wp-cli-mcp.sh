#!/bin/bash
# Start the WP-CLI MCP server (stdio JSON-RPC 2.0).
# Project-agnostic: all per-project config is read at runtime from
# <project-root>/.serena/wp-cli.conf. Nothing project-specific lives here.
#
# Uses PLUGIN_ROOT env var (set by plugin.json) to locate the Python script.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="${PLUGIN_ROOT:-$(dirname "$SCRIPT_DIR")}"

# CLAUDE_PROJECT_DIR tells the server where to find .serena/wp-cli.conf.
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

exec python3 "$PLUGIN_ROOT/hooks/swe_hooks/mcp/wp_cli_server.py"
