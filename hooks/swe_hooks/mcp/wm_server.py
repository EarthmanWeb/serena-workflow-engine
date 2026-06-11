#!/usr/bin/env python3
"""SWE Working Memory MCP Server.

Lightweight stdio MCP server (JSON-RPC 2.0, newline-delimited) exposing
Working Memory update tools. Stdlib only — no external dependencies.

Imports from hooks/swe_hooks/core/ to reuse existing WM functions.
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

# --- sys.path bootstrap (same pattern as tools/set_state.py) ---
_script_dir = os.path.dirname(os.path.abspath(__file__))
_swe_hooks_dir = os.path.dirname(_script_dir)       # mcp/ -> swe_hooks/
_hooks_dir = os.path.dirname(_swe_hooks_dir)         # swe_hooks/ -> hooks/
if _hooks_dir not in sys.path:
    sys.path.insert(0, _hooks_dir)

from swe_hooks.core.config import (
    parse_working_memory_state,
    read_working_memory_state,
    read_state_file,
    write_state_file,
)
from swe_hooks.core.session import (
    find_working_memory_for_session,
    get_project_root,
)

# ──────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "swe-wm"
SERVER_VERSION = "1.0.0"

# Sections that the daemon manages — agent must never touch these
PROTECTED_SECTIONS = {"Workflow Context", "Transitions"}

# Agent-owned sections that can be updated
ALLOWED_SECTIONS = [
    "Current Task", "Progress", "Files", "Notes",
    "Requirements", "Implementation Notes", "Previous Task",
    "Task Context", "Affected Features", "Context", "Feature(s)",
]

VALID_STATUSES = [
    "IN_PROGRESS", "BLOCKED", "COMPLETED", "VERIFY_COMPLETE", "FAILED",
]

# ──────────────────────────────────────────────────────────────────
# Tool definitions (JSON Schema)
# ──────────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "swe_wm_read",
        "description": (
            "Read the current Working Memory state and full content for a session. "
            "Returns workflow context (current state, feature keys, session ID), "
            "the raw markdown content, and the WM file path."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "8-character session ID (e.g., 'ca2d3450'). If omitted, uses SWE_SESSION_ID env var.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "swe_wm_update_section",
        "description": (
            "Update a specific section of Working Memory WITHOUT touching daemon-managed "
            "fields (Current State, Previous State, Transitions, Edit Count, Last Updated). "
            "Targets agent-owned sections only. Uses atomic write to prevent corruption."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "8-character session ID. If omitted, uses SWE_SESSION_ID env var.",
                },
                "section": {
                    "type": "string",
                    "enum": ALLOWED_SECTIONS,
                    "description": "The heading name of the section to update.",
                },
                "content": {
                    "type": "string",
                    "description": "New markdown content for the section (replaces everything between this heading and the next heading of same or higher level).",
                },
                "append": {
                    "type": "boolean",
                    "description": "If true, append content to the section instead of replacing. Default: false.",
                    "default": False,
                },
            },
            "required": ["section", "content"],
        },
    },
    {
        "name": "swe_wm_list",
        "description": (
            "List all Working Memory files for the project. Returns session IDs, "
            "file paths, and modification times. Use this when you need to see WM "
            "files that are hidden from Serena's list_memories by ignored_memory_patterns."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "swe_wm_update_status",
        "description": (
            "Update the task status tag in Current Task (e.g., [IN_PROGRESS] -> [COMPLETED]). "
            "Only modifies the status bracket, not daemon-managed state fields."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "8-character session ID. If omitted, uses SWE_SESSION_ID env var.",
                },
                "status": {
                    "type": "string",
                    "enum": VALID_STATUSES,
                    "description": "New task status tag.",
                },
            },
            "required": ["status"],
        },
    },
]

TOOL_REGISTRY: Dict[str, Any] = {}  # populated after function definitions

# ──────────────────────────────────────────────────────────────────
# Session ID resolution
# ──────────────────────────────────────────────────────────────────

def _resolve_session_id(explicit: str = None) -> Optional[str]:
    """Resolve session_id: explicit param > env vars > most recent WM file."""
    if explicit:
        return explicit
    sid = os.environ.get("SWE_SESSION_ID")
    if sid:
        return sid
    sid = os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        return sid[:8]
    # Fallback: find most recent WM file and extract session ID from filename
    try:
        import glob as _glob
        cwd = get_project_root()
        swe_dir = os.path.join(cwd, '.serena', 'memories')
        wm_files = _glob.glob(os.path.join(swe_dir, 'WM_*.md'))
        if wm_files:
            most_recent = max(wm_files, key=os.path.getmtime)
            match = re.search(r'WM_([a-f0-9]{8})', os.path.basename(most_recent))
            if match:
                return match.group(1)
    except Exception:
        pass
    return None

# ──────────────────────────────────────────────────────────────────
# Tool implementations
# ──────────────────────────────────────────────────────────────────


def _sync_section_to_state_file(session_id: str, section: str, content: str):
    """Sync key WM sections to the JSON state file.

    Maps WM markdown sections to state file fields so state persists
    without the WM markdown file.
    """
    section_lower = section.lower().replace(' ', '_')
    state = read_state_file(session_id)
    if not state:
        return

    updated = False
    if section_lower in ('current_task', 'task_context'):
        # Extract first meaningful line as task summary
        state['task'] = content.split('\n')[0].strip().lstrip('#').strip()
        updated = True
    elif section_lower in ('affected_features', 'feature(s)'):
        features = re.findall(r'\*\*(?:Primary|Secondary)\*\*:\s*(\w+)', content)
        if features:
            state['features'] = features
            updated = True
    elif section_lower == 'progress':
        lines = [l.strip() for l in content.split('\n') if l.strip().startswith('- [x]')]
        if lines:
            state['progress'] = [l.replace('- [x] ', '') for l in lines]
            updated = True

    if updated:
        write_state_file(
            session_id,
            state.get('current_state', 'WF_EXECUTE'),
            prev_state=state.get('prev_state'),
            task=state.get('task'),
            features=state.get('features'),
            progress=state.get('progress'),
        )

def tool_swe_wm_read(session_id: str = None) -> dict:
    """Read WM state and content for a session.

    Returns state from expanded JSON state file (authoritative) merged with
    WM markdown content (display). If WM markdown doesn't exist but state
    file does, returns state-only response.
    """
    session_id = _resolve_session_id(session_id)
    if not session_id:
        return {"error": "No session_id provided and no SWE_SESSION_ID env var set"}

    cwd = get_project_root()

    # Read authoritative state from JSON state file
    state_file = read_state_file(session_id)

    # Read WM markdown (optional display artifact)
    wm_filepath = find_working_memory_for_session(cwd, session_id)
    content = ""
    if wm_filepath:
        with open(wm_filepath, "r") as f:
            content = f.read()

    # Merge: state file is authoritative, WM content for display
    if state_file:
        state = {
            "current_state": state_file.get("current_state"),
            "prev_state": state_file.get("prev_state"),
            "session_id": session_id,
            "task": state_file.get("task", ""),
            "features": state_file.get("features", []),
            "progress": state_file.get("progress", []),
            "return_step": state_file.get("return"),
        }
    elif wm_filepath:
        # Fallback: parse from WM markdown
        state, _ = read_working_memory_state(cwd, session_id=session_id)
    else:
        return {"error": f"No state file or WM found for session {session_id}"}

    return {
        "session_id": session_id,
        "wm_filepath": wm_filepath or "",
        "state": state,
        "content": content,
    }


def tool_swe_wm_update_section(
    section: str, content: str, session_id: str = None, append: bool = False
) -> dict:
    """Update a specific WM section without touching daemon-managed fields.

    Also persists key fields (task, features, progress) to the JSON state file
    so state survives without WM markdown.
    """
    session_id = _resolve_session_id(session_id)
    if not session_id:
        return {"error": "No session_id provided and no SWE_SESSION_ID env var set"}

    if section in PROTECTED_SECTIONS:
        return {"error": f"Section '{section}' is daemon-managed and cannot be updated via this tool"}

    cwd = get_project_root()
    wm_filepath = find_working_memory_for_session(cwd, session_id)
    if not wm_filepath:
        return {"error": f"No WM file found for session {session_id}"}

    with open(wm_filepath, "r") as f:
        wm_content = f.read()

    updated = False

    # Try matching as H3 first, then H2
    for level in [3, 2]:
        hashes = "#" * level
        # Escape section name for regex
        escaped_section = re.escape(section)
        # Match heading + content up to next heading of same or higher level, or EOF
        next_heading = "|".join(re.escape("#" * l) + " " for l in range(1, level + 1))
        pattern = rf"({hashes} {escaped_section}\s*\n)(.*?)(?=\n(?:{next_heading})|\Z)"
        match = re.search(pattern, wm_content, re.DOTALL)
        if match:
            heading = match.group(1)
            old_body = match.group(2)
            if append:
                new_body = old_body.rstrip("\n") + "\n" + content + "\n"
            else:
                new_body = content + "\n"
            wm_content = wm_content[: match.start()] + heading + new_body + wm_content[match.end() :]
            updated = True
            break

    if not updated:
        # Section not found — append as new H2 before "## Previous Task" or at end
        insert_marker = "\n## Previous Task"
        if insert_marker in wm_content:
            wm_content = wm_content.replace(
                insert_marker, f"\n## {section}\n\n{content}\n{insert_marker}", 1
            )
        else:
            wm_content = wm_content.rstrip("\n") + f"\n\n## {section}\n\n{content}\n"

    # Atomic write to WM markdown (display artifact)
    tmp_path = wm_filepath + ".tmp"
    with open(tmp_path, "w") as f:
        f.write(wm_content)
    os.replace(tmp_path, wm_filepath)

    # Persist key fields to JSON state file (authoritative)
    _sync_section_to_state_file(session_id, section, content)

    return {
        "success": True,
        "session_id": session_id,
        "section": section,
        "action": "appended" if append else "replaced",
        "wm_filepath": wm_filepath,
    }


def tool_swe_wm_update_status(status: str, session_id: str = None) -> dict:
    """Update the **[STATUS]**: tag in Current Task."""
    session_id = _resolve_session_id(session_id)
    if not session_id:
        return {"error": "No session_id provided and no SWE_SESSION_ID env var set"}

    if status not in VALID_STATUSES:
        return {"error": f"Invalid status '{status}'. Valid: {VALID_STATUSES}"}

    cwd = get_project_root()
    wm_filepath = find_working_memory_for_session(cwd, session_id)
    if not wm_filepath:
        return {"error": f"No WM file found for session {session_id}"}

    with open(wm_filepath, "r") as f:
        content = f.read()

    # Find **[STATUS]**: pattern
    old_match = re.search(r"\*\*\[([A-Z_]+)\]\*\*:", content)
    old_status = old_match.group(1) if old_match else None

    if old_match:
        content = content[: old_match.start()] + f"**[{status}]**:" + content[old_match.end() :]
    else:
        # No existing tag — inject after ## Current Task heading
        ct_match = re.search(r"(## Current Task\s*\n+)", content)
        if ct_match:
            content = content[: ct_match.end()] + f"**[{status}]**: " + content[ct_match.end() :]

    # Atomic write
    tmp_path = wm_filepath + ".tmp"
    with open(tmp_path, "w") as f:
        f.write(content)
    os.replace(tmp_path, wm_filepath)

    return {
        "success": True,
        "session_id": session_id,
        "old_status": old_status,
        "new_status": status,
        "wm_filepath": wm_filepath,
    }


def tool_swe_wm_list() -> dict:
    """List all WM files in the project's .serena/memories/ directory."""
    import glob as _glob
    from datetime import datetime

    cwd = get_project_root()
    memories_dir = os.path.join(cwd, '.serena', 'memories')
    wm_files = sorted(_glob.glob(os.path.join(memories_dir, 'WM_*.md')), key=os.path.getmtime, reverse=True)

    results = []
    for wm_path in wm_files:
        basename = os.path.basename(wm_path)
        match = re.search(r'WM_([a-f0-9]{8})', basename)
        session_id = match.group(1) if match else None
        mtime = os.path.getmtime(wm_path)
        results.append({
            "session_id": session_id,
            "filename": basename,
            "filepath": wm_path,
            "modified": datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M'),
        })

    return {"wm_files": results, "count": len(results)}


# Register tools
TOOL_REGISTRY = {
    "swe_wm_read": tool_swe_wm_read,
    "swe_wm_list": tool_swe_wm_list,
    "swe_wm_update_section": tool_swe_wm_update_section,
    "swe_wm_update_status": tool_swe_wm_update_status,
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
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error: {e}"}],
            "isError": True,
        }


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

        # Log incoming request
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
            # Log outgoing response
            if method == "tools/call":
                is_err = result.get("isError", False)
                _log(f"[Out] {tool_name}: {'ERROR' if is_err else 'OK'}")
            _send_result(msg_id, result)
        else:
            _log(f"[Out] Method not found: {method}")
            _send_error(msg_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
