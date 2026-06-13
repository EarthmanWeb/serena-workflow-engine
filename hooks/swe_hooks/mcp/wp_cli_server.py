#!/usr/bin/env python3
"""WP-CLI MCP Server.

Lightweight stdio MCP server (JSON-RPC 2.0, newline-delimited) exposing a single
`wp_cli` tool that runs WP-CLI commands against a local Docker container or a
remote host (over WP-CLI's --ssh), for any WordPress project.

Stdlib only — no external dependencies. Mirrors the transport of wm_server.py.

PROJECT-AGNOSTIC: this file contains NO project-specific values. All per-project
configuration (container name, paths, SSH string) is read at runtime from
`<project-root>/.serena/wp-cli.conf`. The plugin ships only this generic server.
"""

import json
import os
import shlex
import subprocess
import sys
from typing import Any, Dict, List, Optional

# ──────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "wp-cli"
SERVER_VERSION = "1.0.0"

CONF_RELATIVE_PATH = os.path.join(".serena", "wp-cli.conf")

# Destructive WP-CLI verb patterns blocked on production unless confirm:true.
# Each entry is a sequence of tokens that must appear as a contiguous prefix
# of the command's leading words (after stripping global --flags).
DESTRUCTIVE_PREFIXES = [
    ["db", "reset"],
    ["db", "drop"],
    ["db", "import"],
    ["db", "clean"],
    ["site", "empty"],
    ["post", "delete"],
    ["term", "delete"],
    ["user", "delete"],
    ["comment", "delete"],
    ["option", "delete"],
    ["plugin", "delete"],
    ["theme", "delete"],
    ["plugin", "uninstall"],
]

# search-replace is destructive unless it carries --dry-run
SEARCH_REPLACE = ["search-replace"]

# ──────────────────────────────────────────────────────────────────
# Tool definitions (JSON Schema)
# ──────────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "wp_cli",
        "description": (
            "Run a WP-CLI command against this project's local Docker WordPress "
            "(default) or its remote production host (over SSH). Configuration is "
            "read from <project-root>/.serena/wp-cli.conf. Pass the WP-CLI command "
            "WITHOUT a leading 'wp' (e.g. args='plugin list --status=active'). "
            "On production, destructive commands (db reset/import, post/user delete, "
            "search-replace without --dry-run, plugin/theme delete, etc.) are blocked "
            "unless confirm=true and the guard is enabled."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "args": {
                    "type": "string",
                    "description": "The WP-CLI command and its flags, without the leading 'wp'. Example: 'option get blogname' or 'plugin list --status=active --format=json'.",
                },
                "target": {
                    "type": "string",
                    "enum": ["local", "production"],
                    "description": "Where to run. 'local' = Docker container (default). 'production' = remote host over WP-CLI --ssh.",
                    "default": "local",
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Required to run a destructive command on production when the guard is enabled. Default: false.",
                    "default": False,
                },
            },
            "required": ["args"],
        },
    },
]

# ──────────────────────────────────────────────────────────────────
# Config loading (per-project, runtime)
# ──────────────────────────────────────────────────────────────────

class ConfigError(Exception):
    """Raised when project config is missing or incomplete."""


def get_project_root() -> str:
    """Project root = CLAUDE_PROJECT_DIR if set, else current working directory."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def load_config() -> Dict[str, str]:
    """Read .serena/wp-cli.conf from the project root.

    Format: KEY=VALUE lines, '#' comments and blank lines ignored.
    Let-it-fail: missing file or missing required keys raise ConfigError with
    a clear message — no silent defaults that would mask misconfiguration.
    """
    root = get_project_root()
    conf_path = os.path.join(root, CONF_RELATIVE_PATH)

    if not os.path.isfile(conf_path):
        raise ConfigError(
            f"No WP-CLI config found at {conf_path}. "
            f"Create it (see wp-cli.conf.example in the swe plugin) with at least "
            f"LOCAL_CONTAINER and LOCAL_PATH."
        )

    conf: Dict[str, str] = {}
    with open(conf_path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            conf[key.strip()] = value.strip().strip('"').strip("'")

    return conf


def require(conf: Dict[str, str], key: str) -> str:
    val = conf.get(key, "")
    if not val:
        raise ConfigError(
            f"Missing required key '{key}' in {CONF_RELATIVE_PATH}."
        )
    return val


def guard_enabled(conf: Dict[str, str]) -> bool:
    return conf.get("PROD_GUARD", "true").lower() not in ("false", "0", "no", "off")


# ──────────────────────────────────────────────────────────────────
# Command construction + destructive detection
# ──────────────────────────────────────────────────────────────────

def _leading_words(arg_tokens: List[str]) -> List[str]:
    """Return the leading non-flag tokens (the WP-CLI command path)."""
    words = []
    for tok in arg_tokens:
        if tok.startswith("-"):
            break
        words.append(tok)
    return words


def is_destructive(arg_tokens: List[str]) -> bool:
    """True if the command matches a destructive prefix.

    search-replace is destructive UNLESS --dry-run is present.
    """
    words = _leading_words(arg_tokens)

    if words[:1] == SEARCH_REPLACE:
        return "--dry-run" not in arg_tokens

    for prefix in DESTRUCTIVE_PREFIXES:
        if words[: len(prefix)] == prefix:
            return True
    return False


def build_command(conf: Dict[str, str], target: str, arg_tokens: List[str]) -> List[str]:
    """Build the full docker exec argv for the requested target.

    local:      docker exec [-w WORKDIR] CONTAINER wp --path=PATH <args> --allow-root
    production: docker exec CONTAINER wp --ssh=REMOTE_SSH <args> --allow-root
    """
    container = require(conf, "LOCAL_CONTAINER")

    cmd: List[str] = ["docker", "exec"]

    if target == "production":
        remote_ssh = require(conf, "REMOTE_SSH")
        cmd += [container, "wp", f"--ssh={remote_ssh}"]
        cmd += arg_tokens
        cmd += ["--allow-root"]
    else:
        path = require(conf, "LOCAL_PATH")
        workdir = conf.get("LOCAL_WORKDIR", "")
        if workdir:
            cmd += ["-w", workdir]
        cmd += [container, "wp", f"--path={path}"]
        cmd += arg_tokens
        cmd += ["--allow-root"]

    return cmd


# ──────────────────────────────────────────────────────────────────
# Tool implementation
# ──────────────────────────────────────────────────────────────────

def tool_wp_cli(args: str, target: str = "local", confirm: bool = False) -> dict:
    if target not in ("local", "production"):
        raise ValueError(f"Invalid target '{target}'. Use 'local' or 'production'.")

    arg_tokens = shlex.split(args)
    if not arg_tokens:
        raise ValueError("'args' is empty — provide a WP-CLI command (without 'wp').")
    if arg_tokens[0] == "wp":
        # Common mistake — strip a leading 'wp' so it still works.
        arg_tokens = arg_tokens[1:]
        if not arg_tokens:
            raise ValueError("'args' contained only 'wp' — provide a command.")

    conf = load_config()

    # Production destructive guard
    if target == "production" and guard_enabled(conf) and is_destructive(arg_tokens):
        if not confirm:
            return {
                "blocked": True,
                "reason": (
                    "Destructive WP-CLI command blocked on production by PROD_GUARD. "
                    "Re-run with confirm=true to proceed."
                ),
                "command": "wp " + " ".join(arg_tokens),
                "target": target,
            }

    full_cmd = build_command(conf, target, arg_tokens)

    proc = subprocess.run(
        full_cmd,
        capture_output=True,
        text=True,
    )

    return {
        "target": target,
        "command": " ".join(shlex.quote(c) for c in full_cmd),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


# Register tools
TOOL_REGISTRY = {
    "wp_cli": tool_wp_cli,
}

# ──────────────────────────────────────────────────────────────────
# JSON-RPC transport
# ──────────────────────────────────────────────────────────────────

def _log(msg: str):
    """Log to stderr (visible in VSCode MCP output panel)."""
    print(f"[{SERVER_NAME}] {msg}", file=sys.stderr, flush=True)


def _send(obj: dict):
    """Write a JSON-RPC message to stdout (newline-delimited)."""
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _send_result(msg_id: Any, result: Any):
    _send({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _send_error(msg_id: Any, code: int, message: str):
    _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


# ──────────────────────────────────────────────────────────────────
# MCP protocol handlers
# ──────────────────────────────────────────────────────────────────

def handle_initialize(params: dict) -> dict:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    }


def handle_tools_list(params: dict) -> dict:
    return {"tools": TOOL_DEFINITIONS}


def handle_tools_call(params: dict) -> dict:
    name = params.get("name", "")
    arguments = params.get("arguments", {})
    tool_fn = TOOL_REGISTRY.get(name)
    if not tool_fn:
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
            "isError": True,
        }
    try:
        result = tool_fn(**arguments)
        is_error = bool(result.get("blocked")) if isinstance(result, dict) else False
        return {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            "isError": is_error,
        }
    except ConfigError as e:
        return {"content": [{"type": "text", "text": f"Config error: {e}"}], "isError": True}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}


HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}

# ──────────────────────────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────────────────────────

def main():
    """Persistent stdio MCP server loop (newline-delimited JSON-RPC 2.0)."""
    _log(f"MCP server started (pid={os.getpid()})")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _send_error(None, -32700, "Parse error")
            continue

        msg_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        if method == "tools/call":
            tool_name = params.get("name", "?")
            tool_args = params.get("arguments", {})
            _log(f"[In] tools/call {tool_name}: {json.dumps(tool_args)}")
        elif method:
            _log(f"[In] {method}")

        # Notifications (no id) — acknowledge silently
        if msg_id is None:
            continue

        handler = HANDLERS.get(method)
        if handler:
            result = handler(params)
            if method == "tools/call":
                is_err = result.get("isError", False)
                _log(f"[Out] {tool_name}: {'ERROR' if is_err else 'OK'}")
            _send_result(msg_id, result)
        else:
            _log(f"[Out] Method not found: {method}")
            _send_error(msg_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
