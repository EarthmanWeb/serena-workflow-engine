#!/bin/bash
# Start the WP-CLI MCP server (stdio JSON-RPC 2.0).
#
# The server is the standalone package `mcp-wp-cli-terminus`, published to PyPI:
#   https://github.com/EarthmanWeb/mcp-wp-cli-terminus
# It is launched with `uvx` (from the `uv` toolchain), so there is ONE source of
# truth — the published package — rather than a copy vendored into this plugin.
#
# Project-agnostic: all per-project config is read at runtime from
# <project-root>/.serena/wp-cli.conf. Nothing project-specific lives here.

# CLAUDE_PROJECT_DIR tells the server where to find .serena/wp-cli.conf. It is
# inherited by the uvx child process.
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Pin to a compatible release range so a future breaking version can't silently
# change behavior. Override the whole spec with WP_CLI_MCP_PACKAGE if needed
# (e.g. a git ref: "git+https://github.com/EarthmanWeb/mcp-wp-cli-terminus").
PACKAGE_SPEC="${WP_CLI_MCP_PACKAGE:-mcp-wp-cli-terminus>=0.1,<1}"

if ! command -v uvx >/dev/null 2>&1; then
  echo "start-wp-cli-mcp: 'uvx' not found. Install the uv toolchain (https://docs.astral.sh/uv/) — e.g. 'brew install uv' — then reload. The wp-cli MCP server runs via 'uvx mcp-wp-cli-terminus'." >&2
  exit 127
fi

exec uvx --from "$PACKAGE_SPEC" mcp-wp-cli-terminus
