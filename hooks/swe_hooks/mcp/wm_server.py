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
from swe_hooks.core.state_manager import perform_transition
from swe_hooks.core.stream import (
    append_event,
    get_stream_path,
    get_feature_sentinel_path,
    collect_values_since_task_start,
    collect_docpending_sources,
    normalize_memory_name,
    is_valid_memory_name,
    is_excluded_memory,
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
    "Compliance Checklist", "Doc Claims Used", "Open Decisions",
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
            "Sections apply in order; the call stops at the first error (earlier "
            "sections stay applied — see `applied` in the error). Cannot "
            "change Current State — use swe_wm_transition for that.\n\n"
            "Affected Features is VERIFIED (WF_CLASSIFY sweep) — grammar:\n"
            "- **Primary**: <KEY> - <reason>\n"
            "- **Memories loaded**: a/A, b/B   (comma-separated; each must have "
            "been read_memory'd this session; ≥1 feature/* or 'no-feature')\n"
            "- **Memories deferred**: c/C   (NOT allowed for links the Primary "
            "feature surfaced)\n"
            "- **Rules planned**: d/D   (each must be cited as `mem:d/D` in the "
            "Compliance Checklist)\n"
            "- **Rules ruled out**: e/E — reason, f/F — reason   (separate entries "
            "with ',' or ';'; every entry needs ' — <reason>')\n"
            "Every link the Primary feature's read surfaced must be read, planned, "
            "or ruled out. Planned citations are found in a Compliance Checklist "
            "section sent in the SAME call (any position in `sections`) or already "
            "in the WM file — order does not matter."
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
            "Targets agent-owned sections only. Uses atomic write to prevent corruption. "
            "Cannot change Current State — use swe_wm_transition for that."
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
    {
        "name": "swe_wm_transition",
        "description": (
            "The ONLY MCP way to change Current State. Validates the target against "
            "states.json (transition matrix + CLARIFY return rules + loop caps + "
            "subflows) — never a raw field write. Writes .serena/swe-state/<id>.state "
            "and appends the WM Transitions line; returns the new state. Use this for "
            "a declared exit a read cannot take on its own, or to drive a transition "
            "explicitly — e.g. WF_RESEARCH's needs_implementation -> WF_CLASSIFY exit."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "8-character session ID. If omitted, uses SWE_SESSION_ID env var.",
                },
                "target_state": {
                    "type": "string",
                    "description": "The FSM state to transition into (e.g. 'WF_CLASSIFY'). Never a subflow (WF_INIT, WF_CLEANUP, WF_RESEARCH_LITE, WF_UPDATE_MEMORY).",
                },
                "reason": {
                    "type": "string",
                    "description": "Why this transition is happening. Required, non-empty.",
                },
                "force": {
                    "type": "boolean",
                    "description": "Skip transition-matrix/CLARIFY/loop-cap validation. Default: false.",
                    "default": False,
                },
            },
            "required": ["target_state", "reason"],
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

# "Memories deferred" line(s) inside an Affected Features write — explicit
# deferral of docpending links the agent chose NOT to read this task. Format is
# forgiving: any memory name (a token containing '/') on a deferred line counts,
# in any layout — one per line OR comma-separated, with or without a free-form
# note. No '<name> — <reason>' shape is required. MULTILINE + findall (NOT a
# single search) so several deferred lines are ALL honored, e.g.
#   - **Memories deferred**: ref/REF_X, dom/DOM_Y
#   - **Memories deferred**: sys/SYS_Z (only used by the admin UI, not touched)
MEMORIES_DEFERRED_RE = re.compile(
    r'\*\*Memories deferred\*\*:?[ \t]*(.*)$', re.IGNORECASE | re.MULTILINE)

# "Primary" feature line — the feature this task is actually working on.
#   - **Primary**: SWE - remove deferral escape-hatch …
# The KEY is the first bareword token after the label; it maps to the
# feature/feature_<key> memory that must NOT be the source of a deferred link.
PRIMARY_FEATURE_RE = re.compile(
    r'\*\*Primary\*\*:?[ \t]*([A-Za-z0-9_-]+)', re.IGNORECASE | re.MULTILINE)

# Explicit declaration that the task has no feature memory (both fuzzy
# searches returned nothing at WF_CLASSIFY 4b) — the sanctioned exception to
# the "list must include a feature/* memory" rule.
NO_FEATURE_TOKEN = 'no-feature'

# Workflow-machinery prefixes excluded from the 4d sweep (wf/WF_CLASSIFY
# exclusion list). Init-chain memories are workflow plumbing, not feature
# knowledge — they are no part of the sweep contract, so ignore them in a
# Memories-loaded list instead of failing the write.
MACHINERY_PREFIXES = ('wf/', 'claude/')

# USER DECISION (2026-09): spec/, report/, research/, and project/ are FULLY
# excluded from the WF_CLASSIFY Feature Knowledge Sweep — never demanded,
# bulk-loaded, or required to carry a disposition. A name in one of these
# topics that shows up as a docpending link (e.g. surfaced by a primary
# feature's `[[spec/SPEC_X]]` link) is dropped from the pending set the same
# way MACHINERY_PREFIXES names are — it is never something the sweep
# verifier can reject the write over. It still loads fine when the task
# explicitly reads it: that shows up as an ordinary docread and an ordinary
# '**Memories loaded**:' entry, which _check_memory_sweep already accepts
# unconditionally (no reject path here examines what a LOADED name's prefix
# is).
#
# Exclusion test is `is_excluded_memory` (hooks/swe_hooks/core/stream.py) —
# the single source of truth shared with hooks/post/swe_post_read_state.py
# and hooks/swe_hooks/core/memory_size.py.

# ──────────────────────────────────────────────────────────────────
# Change Set H — obligation-digest disposition parsing
# ──────────────────────────────────────────────────────────────────
# "Rules planned": digest-tier disposition — obligations captured into the
# Compliance Checklist WITHOUT a body read. Same forgiving grammar as
# "Memories deferred": comma-separated names, one per line or several lines,
# findall so all lines are honored.
#   - **Rules planned**: dom/DOM_X, ref/REF_Y
RULES_PLANNED_RE = re.compile(
    r'\*\*Rules planned\*\*:?[ \t]*(.*)$', re.IGNORECASE | re.MULTILINE)

# "Rules ruled out": each entry REQUIRES a ' — ' reason (unlike deferred /
# planned, which tolerate a bare name). Entries are comma-separated or one
# per line; each entry's reason runs to the next comma or line end.
#   - **Rules ruled out**: ref/REF_X — not applicable, dom/DOM_Y — superseded
RULES_RULED_OUT_RE = re.compile(
    r'\*\*Rules ruled out\*\*:?[ \t]*(.*)$', re.IGNORECASE | re.MULTILINE)

# Compliance Checklist section heading (any level) — citations of
# 'Rules planned' names as `mem:<name>` must appear within it.
COMPLIANCE_CHECKLIST_RE = re.compile(
    r'^#+\s*Compliance Checklist\s*\n(.*?)(?=\n#+\s|\Z)',
    re.IGNORECASE | re.MULTILINE | re.DOTALL)

# `mem:<name>` citation token.
MEM_CITATION_RE = re.compile(r'mem:([A-Za-z0-9_/.-]+)')


def _parse_rules_planned(content: str) -> set:
    """Parse memory names from ALL '**Rules planned**:' line(s).

    Same forgiving grammar as _parse_deferred_names: any token containing
    '/' on a Rules-planned line counts, comma-separated or one per line.
    """
    names = set()
    for line_tail in RULES_PLANNED_RE.findall(content or ''):
        for token in re.split(r'[\s,]+', line_tail):
            token = token.strip('[]`.,;:')
            if '/' not in token:
                continue
            name = normalize_memory_name(token)
            if name and '/' in name:
                names.add(name)
    return names


def _parse_ruled_out(content: str) -> dict:
    """Parse '<name> — <reason>' entries from ALL '**Rules ruled out**:'
    line(s). Returns {normalized_name: reason}. An entry with no ' — '
    reason is returned with reason='' so the caller can reject it by name
    (a missing reason must not silently drop the entry from detection).
    Separator accepts em dash '—', en dash '–', or ' - ', all handled the
    same way."""
    entries = {}
    for line_tail in RULES_RULED_OUT_RE.findall(content or ''):
        # Split entries on commas that are NOT inside a '<name> — <reason>'
        # pair's reason text is impossible to fully disambiguate with commas
        # allowed in reasons, so split entries by the ' — ' anchor instead:
        # walk left-to-right, each entry starts at a memory-name-shaped token.
        # Entry separator: ',' or ';' followed by a memory-name-shaped token.
        for raw_entry in re.split(r'(?<=[^\s])\s*[,;]\s*(?=[A-Za-z0-9_.~-]+/)', line_tail.strip()):
            raw_entry = raw_entry.strip().strip('[]`.,;:')
            if not raw_entry:
                continue
            if '—' in raw_entry:
                name_part, reason_part = raw_entry.split('—', 1)
            elif '–' in raw_entry:
                name_part, reason_part = raw_entry.split('–', 1)
            elif ' - ' in raw_entry:
                name_part, reason_part = raw_entry.split(' - ', 1)
            else:
                name_part, reason_part = raw_entry, ''
            token = name_part.strip().strip('[]`.,;:').split()
            token = token[0] if token else ''
            if '/' not in token:
                continue
            name = normalize_memory_name(token)
            if not name or '/' not in name:
                continue
            entries[name] = reason_part.strip()
    return entries


def _compliance_checklist_body(content: str) -> str:
    """Return the body text of the '## Compliance Checklist' section, or ''
    when absent."""
    match = COMPLIANCE_CHECKLIST_RE.search(content or '')
    return match.group(1) if match else ''


def _cited_mem_names(content: str) -> set:
    """Every `mem:<name>` citation inside the Compliance Checklist section,
    normalized."""
    return _mem_citations(_compliance_checklist_body(content))


def _mem_citations(body: str) -> set:
    """Every `mem:<name>` citation anywhere in `body`, normalized."""
    names = set()
    for token in MEM_CITATION_RE.findall(body or ''):
        name = normalize_memory_name(token.strip('[]`.,;:'))
        if name:
            names.add(name)
    return names


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


def _parse_deferred_names(content: str) -> set:
    """Parse the deferred memory names from ALL '**Memories deferred**:' line(s).

    Forgiving by design: a memory is "deferred" if its name (any token that
    looks like a memory path, i.e. contains a '/') appears ANYWHERE in a
    deferred line. Separators, punctuation, and any reason text are ignored —
    one-per-line, comma-separated, with or without a reason, colons/commas in
    the reason: all accepted. There is NO required '<name> — <reason>' shape.

    Uses findall so several deferred lines are all honored (a single search
    dropped every line but the first).
    """
    names = set()
    for line_tail in MEMORIES_DEFERRED_RE.findall(content or ''):
        for token in re.split(r'[\s,]+', line_tail):
            token = token.strip('[]`.,;:')
            if '/' not in token:
                continue
            name = normalize_memory_name(token)
            if name and '/' in name:
                names.add(name)
    return names


def _parse_primary_feature_memory(content: str):
    """The feature/feature_<key> memory name for the write's **Primary** key,
    or None when no primary key is declared.

    A docpending link surfaced by THIS memory must be read — deferring it is the
    dodge the read-gated rule closes. Links surfaced only by other (paused /
    sibling) feature reads remain deferrable.
    """
    match = PRIMARY_FEATURE_RE.search(content or '')
    if not match:
        return None
    key = match.group(1).strip().lower()
    if not key or key == 'no-feature':
        return None
    return 'feature/feature_' + key


def _collect_session_docreads(stream_path: str) -> set:
    """Collect every normalized 'docread' name from the WHOLE session stream.

    D2 sweep idempotence: the docread ledger is session-wide — a memory read
    in ANY earlier turn/task of this session satisfies a later sweep list, so
    re-listing without re-reading passes. (Docpending accounting keeps its
    narrower since-sweep window; this collector is for loaded-list
    verification only.) Malformed/truncated names are dropped.
    """
    names = set()
    if not os.path.exists(stream_path):
        return names
    try:
        with open(stream_path, 'r') as f:
            lines = f.readlines()
    except IOError:
        return names
    for line in lines:
        try:
            event = json.loads(line.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if event.get('type') != 'docread':
            continue
        value = event.get('name')
        items = value if isinstance(value, list) else [value]
        for v in items:
            if not v:
                continue
            name = normalize_memory_name(str(v))
            if is_valid_memory_name(name):
                names.add(name)
    return names


def _check_memory_sweep(
    session_id: str, content: str, other_sections: Optional[List[Dict[str, Any]]] = None
) -> Optional[str]:
    """Validate an Affected Features write against the ACTUAL memory reads of
    this session (WF_CLASSIFY Step 4d Feature Knowledge Sweep).

    Contract:
      - The write must carry a '**Memories loaded**:' list (absent is allowed
        only once a sweep sentinel already exists for the session/task).
      - Every listed name must have a matching 'docread' stream event
        ANYWHERE in this session's stream — a read in any earlier turn/task
        of the session satisfies the list. The WM 'Memories loaded' line is
        the dedupe ledger: re-listing without re-reading passes; only a name
        never read this session fails. The sweep sentinel stays per-task
        (cleared on WF_CLASSIFY entry), so each task still requires a fresh
        Affected Features WRITE — just not re-reads.
      - The list must include at least one 'feature/*' memory, or the content
        must carry the literal token 'no-feature' (both WF_CLASSIFY 4b fuzzy
        searches returned nothing).
      - Every 'docpending' link surfaced by this task's reads must be
        dispositioned. A link surfaced ONLY by a paused/sibling-feature read
        during a task pivot: read ∪ deferred (named on a '**Memories
        deferred**:' line, any layout, note optional) ∪ planned ∪ ruled-out.
        A link surfaced by the PRIMARY feature (on-topic by construction):
        read ∪ planned ∪ ruled-out — bare deferral is REJECTED (deferring
        asserts "cold for this task", never true of the feature's own link).
      - Change Set H (digest-tier disposition, both OPTIONAL): a
        '**Rules planned**:' name is a docpending link whose obligations were
        captured into the Compliance Checklist WITHOUT a body read — it counts
        toward the satisfaction set ONLY when also cited as `mem:<name>`
        inside a '## Compliance Checklist' section (checked in
        `other_sections` first, then the existing WM file content); an
        uncited planned name is rejected by name. A '**Rules ruled out**:'
        entry likewise counts toward satisfaction, but EVERY entry must carry
        a ' — ' reason or is rejected by name. Absent both lines, only read ∪
        deferred (non-primary) / read (primary) apply.

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

    # D2 sweep idempotence: the docread ledger is the WHOLE session stream —
    # a read in ANY earlier turn/task satisfies the list. The per-task cost
    # is the fresh Affected Features WRITE (sentinel cleared on WF_CLASSIFY
    # entry), never re-reading.
    read_names = _collect_session_docreads(get_stream_path(session_id))
    unread = sorted(listed - read_names)
    if unread:
        return (
            "Sweep verification FAILED — listed but never read this "
            f"session: {', '.join(unread)}. read_memory each of them, then "
            "re-run this update. Prior-turn reads count; do not re-read "
            "memories already read earlier this session."
        )

    # Docpending enforcement: every related link surfaced by this task's reads
    # must be either read or named on a '**Memories deferred**:' line (format is
    # forgiving — see _parse_deferred_names). A link surfaced by the CURRENT
    # primary feature must be READ, not deferred (on-topic by construction);
    # deferral is for links raised by a paused/sibling-feature read during a
    # pivot.
    deferred = _parse_deferred_names(content)

    # Change Set H — digest-tier dispositions (both optional; absent lines =
    # today's behavior unchanged).
    planned = _parse_rules_planned(content)
    ruled_out = _parse_ruled_out(content)

    if planned:
        # Citation lookup order: this call's OTHER sections first (a
        # Compliance Checklist written earlier/later in the same batched
        # swe_wm_update call), then the existing WM file content on disk.
        cited = set()
        for spec in (other_sections or []):
            if not isinstance(spec, dict):
                continue
            spec_content = str(spec.get('content', ''))
            # A sibling 'Compliance Checklist' spec's content IS the section
            # body (no heading) — every citation in it counts.
            if spec.get('section') == 'Compliance Checklist':
                cited |= _mem_citations(spec_content)
            else:
                cited |= _cited_mem_names(spec_content)
        cited |= _cited_mem_names(content)
        cwd = get_project_root()
        wm_filepath = find_working_memory_for_session(cwd, session_id)
        if wm_filepath and os.path.exists(wm_filepath):
            try:
                with open(wm_filepath, 'r') as f:
                    cited |= _cited_mem_names(f.read())
            except IOError:
                pass
        uncited = sorted(planned - cited)
        if uncited:
            return (
                "Sweep verification FAILED — 'Rules planned' names not cited "
                f"as `mem:<name>` inside a '## Compliance Checklist' section: "
                f"{', '.join(uncited)}. Add a `mem:{uncited[0]}`-style citation "
                "for each in the Compliance Checklist, then re-run this update."
            )

    if ruled_out:
        unreasoned = sorted(n for n, reason in ruled_out.items() if not reason)
        if unreasoned:
            return (
                "Sweep verification FAILED — 'Rules ruled out' entries with no "
                f"' — <reason>': {', '.join(unreasoned)}. Every ruled-out entry "
                "needs a reason, e.g. '- **Rules ruled out**: "
                f"{unreasoned[0]} — not applicable to this task'."
            )

    stream_path = get_stream_path(session_id)
    # Docpending is accounted since the LAST successful sweep (not the whole
    # task): once a sweep passes, its links are settled, so a later sweep in the
    # same session only reckons with NEW links. Prevents prior work's links from
    # re-blocking an unrelated follow-up (the cross-task accumulation bug).
    pending = collect_values_since_task_start(
        stream_path, count_type='docpending', value_key='new', since_sweep=True)
    pending = {n for n in pending
               if not n.startswith(MACHINERY_PREFIXES)
               and not is_excluded_memory(n)}
    sources = collect_docpending_sources(stream_path, since_sweep=True)
    primary_mem = _parse_primary_feature_memory(content)

    # Links whose source set INCLUDES the primary feature memory are not
    # deferrable — they must be read (subtract only what was actually read).
    primary_pending = {
        n for n in pending
        if primary_mem and primary_mem in sources.get(n, set())
    }
    other_pending = pending - primary_pending

    # Primary-surfaced links: read ∪ planned (cited) ∪ ruled-out (reasoned)
    # satisfy the link — bare deferral does NOT (deferral asserts "cold",
    # which is never true of a link the feature you are working on links to;
    # planned/ruled-out require the same citation/reason discipline already
    # enforced above). Other (paused/sibling) links keep read ∪ deferred ∪
    # planned ∪ ruled-out.
    primary_dispositioned = read_names | planned | set(ruled_out.keys())
    must_disposition = sorted(primary_pending - primary_dispositioned)
    if must_disposition:
        names = ', '.join(must_disposition)
        example = must_disposition[0]
        return (
            "Sweep verification FAILED — related docs surfaced by the PRIMARY "
            f"feature ({primary_mem}) must be READ, PLANNED, or RULED OUT — "
            f"bare deferral is rejected: {names}. For EACH one, do ONE of:\n"
            "  1. read_memory it, OR\n"
            "  2. plan it — cite it as `mem:<name>` inside a '## Compliance "
            "Checklist' section AND name it on a '**Rules planned**:' line, "
            "e.g. '- **Rules planned**: " + example + "' with "
            "'`mem:" + example + "`' in the Compliance Checklist, OR\n"
            "  3. rule it out — name it on a '**Rules ruled out**:' line with "
            "a ' — <reason>', e.g. '- **Rules ruled out**: " + example + " — "
            "not applicable to this task'.\n"
            "A link the feature you are working on links to is on-topic by "
            "construction — deferral (asserting it is cold) is reserved for "
            "links raised by a paused/other-feature read during a pivot.\n"
            f"Parsed as ruled out: {', '.join(sorted(ruled_out)) or '(none)'} — "
            "if a name you ruled out is missing there, separate entries with "
            "',' or ';' and start each with the memory name."
        )
    dispositioned = deferred | planned | set(ruled_out.keys())
    outstanding = sorted(other_pending - read_names - dispositioned)
    if outstanding:
        names = ', '.join(outstanding)
        return (
            "Sweep verification FAILED — related docs surfaced this task are "
            f"neither read nor deferred: {names}. For EACH one, do ONE of:\n"
            "  1. read_memory it (if it could bear on what this task changes "
            "or inspects), OR\n"
            "  2. defer it — just add its name to a '**Memories deferred**:' "
            "line in the Affected Features section. Put the names there however "
            "you like: one per line or comma-separated, with or without a "
            "note. A note is optional and free-form.\n"
            "Example:\n"
            f"  - **Memories deferred**: {names}\n"
            "Then re-run this update. Don't blanket-defer everything just to "
            "pass — deferring a doc asserts it is cold for THIS task."
        )

    try:
        os.makedirs(os.path.dirname(sentinel), exist_ok=True)
        with open(sentinel, 'w') as f:
            json.dump({"session_id": session_id, "memories": sorted(listed),
                       "deferred": sorted(deferred),
                       "planned": sorted(planned),
                       "ruled_out": sorted(ruled_out.keys())},
                      f, separators=(',', ':'))
    except IOError:
        pass
    # Stamp a sweep marker so the NEXT sweep this session only accounts for
    # docpending links surfaced after this point (see events_since_task_start
    # since_sweep). Settles this sweep's docpending window.
    append_event(stream_path, 'sweep', s=session_id)
    return None


def tool_swe_wm_update_section(
    section: str, content: str, session_id: str = None, append: bool = False,
    other_sections: Optional[List[Dict[str, Any]]] = None,
) -> dict:
    """Update a specific WM section without touching daemon-managed fields.

    Also persists key fields (task, features, progress) to the JSON state file
    so state survives without WM markdown.

    `other_sections` (internal, only passed by tool_swe_wm_update): the OTHER
    section specs in the same batched call — lets the Affected Features sweep
    check see a Compliance Checklist section written in the same call before
    it lands on disk.
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
        sweep_error = _check_memory_sweep(session_id, content, other_sections=other_sections)
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
        siblings = [s for j, s in enumerate(sections or []) if j != i]
        result = tool_swe_wm_update_section(
            spec["section"], spec["content"],
            session_id=session_id, append=bool(spec.get("append", False)),
            other_sections=siblings,
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


def tool_swe_wm_transition(target_state: str, reason: str, session_id: str = None,
                            force: bool = False) -> dict:
    """The ONLY MCP way to change Current State. Delegates to the shared
    perform_transition driver (core.state_manager) — same validation and
    side effects as the set_state.py CLI, using the project root this server
    already resolves for every other tool."""
    session_id = _resolve_session_id(session_id)
    if not session_id:
        return {"error": "No session_id provided and no SWE_SESSION_ID env var set — pass session_id explicitly (it is printed in every workflow hook message, e.g. WM[<id>] / session=\"<id>\")"}

    if not reason or not str(reason).strip():
        return {"error": "reason is required and must be non-empty."}

    if not target_state:
        return {"error": "target_state is required."}

    cwd = get_project_root()
    result = perform_transition(cwd, session_id, target_state, force=bool(force), reason=reason)

    if not result.get("success"):
        return result

    result["summary"] = (
        f"✅ WM[{session_id}] transitioned {result['previous_state']} → "
        f"{result['new_state']}" + (" (forced)" if result.get("forced") else "")
    )
    return result


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
    "swe_wm_transition": tool_swe_wm_transition,
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


def _error_headline(name: str, arguments: dict, result: dict) -> str:
    """Build the ❌ WM[<session>] <tool/section>: <short cause> first line.

    Mirrors the ✅ success-line style (same WM[<id>] bracket) so both render
    identically in a renderer that only shows the first line of output. The
    session id comes from the result (tools that resolved one echo it back)
    or falls back to the request's own session_id argument, then '—' when
    neither is available (e.g. "no session_id" errors). Cause is the raw
    error string, truncated so the whole line stays under ~120 chars.
    """
    session_id = result.get("session_id") or arguments.get("session_id") or "—"
    # Section-scoped errors (from swe_wm_update's "sections[i] (Section): ...")
    # already name their section; otherwise fall back to the tool name and any
    # explicit `section`/`status` argument for context.
    label = name
    if "section" in arguments and name != "swe_wm_update":
        label = f"{name} ({arguments['section']})"
    elif "status" in arguments and name == "swe_wm_update_status":
        label = f"{name} ({arguments['status']})"

    cause = str(result.get("error", "")).strip()
    prefix = f"❌ WM[{session_id}] {label}: "
    budget = max(20, 120 - len(prefix))
    if len(cause) > budget:
        cause = cause[: budget - 1].rstrip() + "…"
    return prefix + cause


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
        # summary — those still emit full JSON.
        if isinstance(result, dict) and result.get("summary") and not result.get("error"):
            text = result["summary"]
        elif isinstance(result, dict) and result.get("error"):
            # Error results: readable ❌ headline first (renderer shows only the
            # first ~3 lines), blank line, then the existing JSON UNCHANGED so
            # callers that parse the JSON body keep working.
            headline = _error_headline(name, arguments, result)
            text = headline + "\n\n" + json.dumps(result, indent=2)
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
