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
from swe_hooks.core.stream import (
    get_stream_path,
    get_feature_sentinel_path,
    collect_values_since_task_start,
    normalize_memory_name,
)

# ──────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "swe-wm"
SERVER_VERSION = "1.1.0"

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
        "name": "swe_wm_update",
        "description": (
            "Batched Working Memory update — apply an optional status change and "
            "any number of section updates in ONE call (replaces serial "
            "swe_wm_update_section/swe_wm_update_status calls). Returns the "
            "post-update workflow state, so a separate swe_wm_read is not needed. "
            "Sections apply in order; the call stops at the first error."
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
                    "description": "Optional task status tag, applied before the section updates.",
                },
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section": {
                                "type": "string",
                                "enum": ALLOWED_SECTIONS,
                                "description": "The heading name of the section to update.",
                            },
                            "content": {
                                "type": "string",
                                "description": "New markdown content for the section.",
                            },
                            "append": {
                                "type": "boolean",
                                "description": "If true, append instead of replacing. Default: false.",
                                "default": False,
                            },
                        },
                        "required": ["section", "content"],
                    },
                    "description": "Section updates applied in order.",
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
    """Resolve session_id: explicit param > env vars > None (fail loud).

    ⛔ NO most-recent-WM guessing. With two sessions on one project, the
    most-recently-modified WM belongs to WHICHEVER session wrote last — reads
    answer for the wrong session and sweep verification runs against the
    wrong session's stream (rejecting memories the active session read, and
    creating the sweep sentinel for the wrong session id). Every workflow
    hook message prints the session id; callers pass it explicitly.
    """
    if explicit:
        return explicit
    sid = os.environ.get("SWE_SESSION_ID")
    if sid:
        return sid
    sid = os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        return sid[:8]
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
        # Extract the first meaningful TASK line as the summary.
        # The section's first line is often a metadata bullet
        # ("- **Feature(s)**: ...", "- **Complexity**: ...") or a heading,
        # NOT the task description. Taking content.split('\n')[0] blindly wrote
        # those bullets into state['task'] (e.g. "- **Feature(s)**: FORMS ...").
        # Prefer an explicit "**Task**:" line; else the first non-metadata,
        # non-heading, non-empty line; else leave the existing task unchanged.
        task_summary = None
        for raw in content.split('\n'):
            line = raw.strip()
            if not line:
                continue
            # Explicit task field wins: "- **Task**: foo" / "**Task**: foo"
            m = re.match(r'^[-*]?\s*\*\*Task\*\*:\s*(.+)$', line, re.IGNORECASE)
            if m:
                task_summary = m.group(1).strip()
                break
            # Skip headings and known metadata bullets.
            if line.startswith('#'):
                continue
            if re.match(r'^[-*]\s*\*\*(Feature\(s\)|Features?|Complexity|'
                        r'Affected Features?|Status|Priority)\*\*', line,
                        re.IGNORECASE):
                continue
            # First genuine content line (strip a leading bullet marker).
            task_summary = re.sub(r'^[-*]\s*', '', line).lstrip('#').strip()
            break
        if task_summary:
            state['task'] = task_summary
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
        return {"error": "No session_id provided and no SWE_SESSION_ID env var set — pass session_id explicitly (it is printed in every workflow hook message, e.g. WM[<id>] / session=\"<id>\")"}

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


# "Memories loaded" line inside an Affected Features write, e.g.
#   - **Memories loaded**: feature/FEATURE_X, dom/DOM_X, ref/REF_Y
MEMORIES_LOADED_RE = re.compile(
    r'\*\*Memories loaded\*\*:?[ \t]*(.*)$', re.IGNORECASE | re.MULTILINE)

# "Memories deferred" line inside an Affected Features write — explicit
# deferral of docpending-linked memories the agent chose NOT to read this
# task. Entries are "<name> — <reason>", comma-separated, e.g.
#   - **Memories deferred**: ref/REF_X — cold: admin UI only, dom/DOM_Y — sibling detail
MEMORIES_DEFERRED_RE = re.compile(
    r'\*\*Memories deferred\*\*:?[ \t]*(.*)$', re.IGNORECASE | re.MULTILINE)

# Explicit declaration that the task has no feature memory (both fuzzy
# searches returned nothing at WF_CLASSIFY 4b) — the sanctioned exception to
# the "list must include a feature/* memory" rule.
NO_FEATURE_TOKEN = 'no-feature'

# Workflow-machinery prefixes excluded from the 4d sweep (wf/WF_CLASSIFY
# exclusion list). Init-chain memories are read BEFORE the task boundary
# (the state event into WF_CLASSIFY), so their docreads can never verify —
# ignore them in a Memories-loaded list instead of failing the write.
MACHINERY_PREFIXES = ('wf/', 'claude/')


def _parse_memories_loaded(content: str) -> Optional[set]:
    """Parse the '**Memories loaded**:' list from an Affected Features write.

    Returns a set of normalized names, or None when the line is absent.
    An empty set means the line exists but lists nothing.
    """
    match = MEMORIES_LOADED_RE.search(content or '')
    if not match:
        return None
    names = set()
    for part in match.group(1).split(','):
        # Memory names never contain whitespace — anything after the first
        # token is agent annotation ("index/INDEX_FEATURES (no match)",
        # "feature/FEATURE_X - primary") and must not poison the name.
        tokens = part.strip().strip('[]`').split()
        if not tokens:
            continue
        name = normalize_memory_name(tokens[0].strip('[]`'))
        if name and '/' in name:
            names.add(name)
    return names


def _parse_memories_deferred(content: str):
    """Parse the '**Memories deferred**:' list from an Affected Features write.

    Returns (names, reasonless): the set of normalized deferred names, and the
    subset listed WITHOUT a reason (nothing after the name in its entry).
    Reason fragments containing commas split into name-less fragments, which
    are ignored (no '/' in the first token).
    """
    match = MEMORIES_DEFERRED_RE.search(content or '')
    if not match:
        return set(), set()
    names, reasonless = set(), set()
    for part in match.group(1).split(','):
        tokens = part.strip().strip('[]`').split()
        if not tokens:
            continue
        name = normalize_memory_name(tokens[0].strip('[]`'))
        if not name or '/' not in name:
            continue
        names.add(name)
        # A reason is any text after the name token (e.g. "— cold: admin UI").
        if len(tokens) < 2 or not ''.join(tokens[1:]).strip('—-–:'):
            reasonless.add(name)
    return names, reasonless


def _check_memory_sweep(session_id: str, content: str) -> Optional[str]:
    """Validate an Affected Features write against the ACTUAL memory reads of
    the current task (WF_CLASSIFY Step 4d Feature Knowledge Sweep).

    Contract:
      - The write must carry a '**Memories loaded**:' list (absent is allowed
        only once a sweep sentinel already exists for the session/task).
      - Every listed name must have a matching 'docread' stream event SINCE
        the current task started (reads from a prior task never count).
      - The list must include at least one 'feature/*' memory, or the content
        must carry the literal token 'no-feature' (both WF_CLASSIFY 4b fuzzy
        searches returned nothing).
      - Every 'docpending' link surfaced by this task's reads must be read or
        explicitly deferred with a reason on a '**Memories deferred**:' line.

    On success creates the 'sweep' sentinel that unlocks the edit gate.
    Returns an error string on violation, None on pass/skip.
    """
    listed = _parse_memories_loaded(content)
    if listed:
        # Drop workflow-machinery names (init chain, read pre-boundary and
        # excluded from the sweep contract) rather than rejecting the write.
        listed = {n for n in listed
                  if not n.startswith(MACHINERY_PREFIXES)}
    sentinel = get_feature_sentinel_path(session_id, 'sweep')

    if listed is None:
        if os.path.exists(sentinel):
            return None  # sweep already verified this task; free-form update
        return (
            "Affected Features must record the Feature Knowledge Sweep: include "
            "a '- **Memories loaded**: <name>, <name>, …' line listing every "
            "memory read for this task (WF_CLASSIFY Step 4e)."
        )

    if not listed:
        return (
            "'**Memories loaded**:' lists no memory names (wf/* and claude/* "
            "workflow memories do not count). Enumerate and read the full "
            "WF_CLASSIFY 4d sweep set (primary feature + its "
            "ARCH_/DOM_/REF_/SYS_ related memories), then list them."
        )

    if (not any(n.startswith('feature/') for n in listed)
            and NO_FEATURE_TOKEN not in (content or '').lower()):
        return (
            "Memories loaded lists no feature/* memory. Load the primary "
            "FEATURE_[KEY] (WF_CLASSIFY Step 4c), or — only when BOTH fuzzy "
            "searches (4b) returned nothing — state 'no-feature' in the section."
        )

    read_names = collect_values_since_task_start(get_stream_path(session_id))
    unread = sorted(listed - read_names)
    if unread:
        return (
            "Sweep verification FAILED — listed but not actually read this "
            f"task: {', '.join(unread)}. read_memory each of them, then re-run "
            "this update. Reads from a previous task in this session do not "
            "count; the sweep is per-task."
        )

    # Docpending enforcement: every related link surfaced by this task's reads
    # must be read or EXPLICITLY deferred with a reason — silent skipping is
    # what forces the operator to prompt "read all related docs" manually.
    deferred, reasonless = _parse_memories_deferred(content)
    if reasonless:
        return (
            "'**Memories deferred**:' entries need a reason: "
            f"{', '.join(sorted(reasonless))}. Format: <name> — <short reason> "
            "(e.g. 'ref/REF_X — cold: admin UI only')."
        )
    pending = collect_values_since_task_start(
        get_stream_path(session_id), count_type='docpending', value_key='new')
    pending = {n for n in pending if not n.startswith(MACHINERY_PREFIXES)}
    outstanding = sorted(pending - read_names - deferred)
    if outstanding:
        return (
            "Sweep verification FAILED — related docs surfaced this task are "
            f"neither read nor deferred: {', '.join(outstanding)}. For each: "
            "read_memory it if it could bear on what this task changes or "
            "inspects, OTHERWISE add it to a '- **Memories deferred**: <name> "
            "— <reason>' line in this section. Then re-run this update. Do "
            "not blanket-defer: deferral asserts the doc is cold for THIS "
            "task."
        )

    try:
        os.makedirs(os.path.dirname(sentinel), exist_ok=True)
        with open(sentinel, 'w') as f:
            json.dump({"session_id": session_id, "memories": sorted(listed),
                       "deferred": sorted(deferred)},
                      f, separators=(',', ':'))
    except IOError:
        pass
    return None


def tool_swe_wm_update_section(
    section: str, content: str, session_id: str = None, append: bool = False
) -> dict:
    """Update a specific WM section without touching daemon-managed fields.

    Also persists key fields (task, features, progress) to the JSON state file
    so state survives without WM markdown.
    """
    session_id = _resolve_session_id(session_id)
    if not session_id:
        return {"error": "No session_id provided and no SWE_SESSION_ID env var set — pass session_id explicitly (it is printed in every workflow hook message, e.g. WM[<id>] / session=\"<id>\")"}

    if section in PROTECTED_SECTIONS:
        return {"error": f"Section '{section}' is daemon-managed and cannot be updated via this tool"}

    # Affected Features writes carry the Feature Knowledge Sweep record —
    # verify every listed memory was ACTUALLY read this task before accepting
    # (creates the 'sweep' sentinel that unlocks the edit gate on pass).
    if section == "Affected Features":
        sweep_error = _check_memory_sweep(session_id, content)
        if sweep_error:
            return {"error": sweep_error}

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

    action = "appended" if append else "replaced"
    return {
        "success": True,
        "session_id": session_id,
        "section": section,
        "action": action,
        "wm_filepath": wm_filepath,
        "summary": f"✅ WM[{session_id}] {section} {action}",
    }


def tool_swe_wm_update_status(status: str, session_id: str = None) -> dict:
    """Update the **[STATUS]**: tag in Current Task."""
    session_id = _resolve_session_id(session_id)
    if not session_id:
        return {"error": "No session_id provided and no SWE_SESSION_ID env var set — pass session_id explicitly (it is printed in every workflow hook message, e.g. WM[<id>] / session=\"<id>\")"}

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
        "summary": f"✅ WM[{session_id}] status {old_status or '—'} → {status}",
    }


def tool_swe_wm_update(
    sections: List[Dict[str, Any]] = None, status: str = None, session_id: str = None
) -> dict:
    """Batched WM update: optional status + ordered section updates in one call.

    Applies status first, then each section via the same code paths as the
    single-purpose tools. Stops at the first error and reports what succeeded.
    Returns the post-update workflow state so a follow-up read is unnecessary.
    """
    session_id = _resolve_session_id(session_id)
    if not session_id:
        return {"error": "No session_id provided and no SWE_SESSION_ID env var set — pass session_id explicitly (it is printed in every workflow hook message, e.g. WM[<id>] / session=\"<id>\")"}
    if not status and not sections:
        return {"error": "Nothing to do: provide `status` and/or `sections`"}

    applied = []

    if status:
        result = tool_swe_wm_update_status(status, session_id=session_id)
        if result.get("error"):
            return {"error": result["error"], "applied": applied}
        applied.append(f"status {result.get('old_status') or '—'} → {status}")

    for i, spec in enumerate(sections or []):
        if not isinstance(spec, dict) or "section" not in spec or "content" not in spec:
            return {
                "error": f"sections[{i}] must be an object with `section` and `content`",
                "applied": applied,
            }
        result = tool_swe_wm_update_section(
            spec["section"], spec["content"],
            session_id=session_id, append=bool(spec.get("append", False)),
        )
        if result.get("error"):
            return {"error": f"sections[{i}] ({spec['section']}): {result['error']}", "applied": applied}
        applied.append(f"{spec['section']} {result['action']}")

    state_file = read_state_file(session_id) or {}
    state = {
        "current_state": state_file.get("current_state"),
        "prev_state": state_file.get("prev_state"),
        "task": state_file.get("task", ""),
        "features": state_file.get("features", []),
    }

    return {
        "success": True,
        "session_id": session_id,
        "applied": applied,
        "state": state,
        "summary": f"✅ WM[{session_id}] " + "; ".join(applied),
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
    "swe_wm_update": tool_swe_wm_update,
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
        # Prefer a one-line human-readable summary when the tool provides one
        # (mutating tools do). Read/list tools return structured data with no
        # summary — those still emit full JSON. Errors keep JSON too, for detail.
        if isinstance(result, dict) and result.get("summary") and not result.get("error"):
            text = result["summary"]
        else:
            text = json.dumps(result, indent=2)
        return {"content": [{"type": "text", "text": text}]}
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
