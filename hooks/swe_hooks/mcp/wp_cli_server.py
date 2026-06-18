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
            "Run a WP-CLI command against a configured WordPress site's local Docker "
            "container (default) or its remote production host (over SSH). Configuration "
            "is read from <project-root>/.serena/wp-cli.conf, which may define one or "
            "MANY sites. Pass the WP-CLI command WITHOUT a leading 'wp' "
            "(e.g. args='plugin list --status=active'). "
            "When the conf defines multiple sites, pass 'site' = the site's top-level "
            "folder name (e.g. 'convenely-pleasurehuntfestival-com'); omit it to use the "
            "configured DEFAULT_SITE or the sole site. "
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
                "site": {
                    "type": "string",
                    "description": "Which configured site to target — the site's top-level folder name (matches a [site:NAME] section in wp-cli.conf). Omit to use DEFAULT_SITE, or the sole site if only one is configured.",
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


def load_config() -> Dict[str, Any]:
    """Read .serena/wp-cli.conf from the project root.

    One format, sectioned INI:

        # top-level globals
        DEFAULT_SITE=my-site
        PROD_GUARD=true

        [site:my-site]
        LOCAL_CONTAINER=my-site-devcontainer-1
        LOCAL_PATH=/workspaces/my-site/public_html
        LOCAL_WORKDIR=/workspaces/my-site
        REMOTE_SSH=user@host:22/path        # optional

    A single-project setup is simply this same format with one [site:NAME]
    section. There is no separate "flat" shape.

    Returns: {"globals": {KEY: VALUE}, "sites": {NAME: {KEY: VALUE}}}.

    Let-it-fail: missing file, no sections, or duplicate sections raise
    ConfigError with a clear message — no silent defaults.
    """
    root = get_project_root()
    conf_path = os.path.join(root, CONF_RELATIVE_PATH)

    if not os.path.isfile(conf_path):
        raise ConfigError(
            f"No WP-CLI config found at {conf_path}. "
            f"Run /swe-wp-cli-setup to generate it (see wp-cli.conf.example in the "
            f"swe plugin for the format)."
        )

    globals_: Dict[str, str] = {}
    sites: Dict[str, Dict[str, str]] = {}
    current: Optional[Dict[str, str]] = None  # None = global scope

    with open(conf_path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("[") and line.endswith("]"):
                header = line[1:-1].strip()
                if not header.startswith("site:"):
                    raise ConfigError(
                        f"Unknown section header '[{header}]' in {CONF_RELATIVE_PATH}. "
                        f"Only [site:NAME] sections are allowed."
                    )
                name = header[len("site:"):].strip()
                if not name:
                    raise ConfigError(
                        f"Empty site name in section header in {CONF_RELATIVE_PATH}."
                    )
                if name in sites:
                    raise ConfigError(
                        f"Duplicate [site:{name}] section in {CONF_RELATIVE_PATH}."
                    )
                current = {}
                sites[name] = current
                continue

            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if current is None:
                globals_[key.strip()] = value
            else:
                current[key.strip()] = value

    if not sites:
        raise ConfigError(
            f"No [site:NAME] sections found in {CONF_RELATIVE_PATH}. "
            f"Run /swe-wp-cli-setup to (re)generate it."
        )

    return {"globals": globals_, "sites": sites}


def resolve_site(conf: Dict[str, Any], site: Optional[str]) -> Dict[str, str]:
    """Pick the target site's config block.

    Resolution order: explicit `site` arg → DEFAULT_SITE global → sole site.
    Ambiguity (multiple sites, no arg, no DEFAULT_SITE) is an error.
    """
    sites: Dict[str, Dict[str, str]] = conf["sites"]
    names = sorted(sites.keys())

    if site:
        if site not in sites:
            raise ConfigError(
                f"Unknown site '{site}'. Configured sites: {', '.join(names)}."
            )
        return sites[site]

    default = conf["globals"].get("DEFAULT_SITE", "")
    if default:
        if default not in sites:
            raise ConfigError(
                f"DEFAULT_SITE='{default}' has no matching [site:{default}] section. "
                f"Configured sites: {', '.join(names)}."
            )
        return sites[default]

    if len(sites) == 1:
        return sites[names[0]]

    raise ConfigError(
        f"Multiple sites configured and no 'site' given (and no DEFAULT_SITE set). "
        f"Pass site=<name>. Configured sites: {', '.join(names)}."
    )


def require(block: Dict[str, str], key: str, site_name: str = "") -> str:
    val = block.get(key, "")
    if not val:
        where = f"[site:{site_name}] in " if site_name else ""
        raise ConfigError(
            f"Missing required key '{key}' in {where}{CONF_RELATIVE_PATH}."
        )
    return val


def guard_enabled(conf: Dict[str, Any]) -> bool:
    return conf["globals"].get("PROD_GUARD", "true").lower() not in ("false", "0", "no", "off")


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


def build_command(block: Dict[str, str], site_name: str, target: str, arg_tokens: List[str]) -> List[str]:
    """Build the full docker exec argv for the requested target.

    local:      docker exec [-w WORKDIR] CONTAINER wp --path=PATH <args> --allow-root
    production: docker exec CONTAINER wp --ssh=REMOTE_SSH <args> --allow-root
    """
    container = require(block, "LOCAL_CONTAINER", site_name)

    cmd: List[str] = ["docker", "exec"]

    if target == "production":
        remote_ssh = require(block, "REMOTE_SSH", site_name)
        cmd += [container, "wp", f"--ssh={remote_ssh}"]
        cmd += arg_tokens
        cmd += ["--allow-root"]
    else:
        path = require(block, "LOCAL_PATH", site_name)
        workdir = block.get("LOCAL_WORKDIR", "")
        if workdir:
            cmd += ["-w", workdir]
        cmd += [container, "wp", f"--path={path}"]
        cmd += arg_tokens
        cmd += ["--allow-root"]

    return cmd


# ──────────────────────────────────────────────────────────────────
# Tool implementation
# ──────────────────────────────────────────────────────────────────

def tool_wp_cli(args: str, site: Optional[str] = None, target: str = "local", confirm: bool = False) -> dict:
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
    block = resolve_site(conf, site)
    resolved_name = site or conf["globals"].get("DEFAULT_SITE", "") or sorted(conf["sites"])[0]

    # Production destructive guard
    if target == "production" and guard_enabled(conf) and is_destructive(arg_tokens):
        if not confirm:
            return {
                "blocked": True,
                "reason": (
                    "Destructive WP-CLI command blocked on production by PROD_GUARD. "
                    "Re-run with confirm=true to proceed."
                ),
                "site": resolved_name,
                "command": "wp " + " ".join(arg_tokens),
                "target": target,
            }

    full_cmd = build_command(block, resolved_name, target, arg_tokens)

    proc = subprocess.run(
        full_cmd,
        capture_output=True,
        text=True,
    )

    return {
        "site": resolved_name,
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
