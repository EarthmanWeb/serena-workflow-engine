"""Configuration and path helpers for SWE hooks.

State is stored in WORKING_MEMORY files (session-isolated), NOT in a global state file.
This allows multiple concurrent sessions without state conflicts.
"""

import json
import os
import re
import glob
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime


_PROJECT_ROOT = None


def get_project_root() -> str:
    """Get project root — the git repository root. Cached after first call.

    Resolution order:
    1. CLAUDE_PROJECT_DIR env var, but only if it contains .git/.
       In multi-root workspaces Claude Code may set this to a subdirectory
       (e.g. .claude/), not the repo root.
    2. Walk up from cwd looking for .git/ (always exists before any plugin
       runs, unlike .serena/ which the plugin itself creates).
    """
    global _PROJECT_ROOT
    if _PROJECT_ROOT is not None:
        return _PROJECT_ROOT

    # Primary: CLAUDE_PROJECT_DIR — but validate it is actually the repo root
    project_dir = os.environ.get('CLAUDE_PROJECT_DIR', '')
    if project_dir and os.path.isdir(os.path.join(project_dir, '.git')):
        _PROJECT_ROOT = project_dir
        return _PROJECT_ROOT

    # Fallback: walk up from cwd looking for .git/
    current = os.getcwd()
    while current != os.path.dirname(current):
        if os.path.isdir(os.path.join(current, '.git')):
            _PROJECT_ROOT = current
            return _PROJECT_ROOT
        current = os.path.dirname(current)

    _PROJECT_ROOT = os.getcwd()
    return _PROJECT_ROOT


# Marketplace/plugin identity for installed_plugins.json lookups.
_PLUGIN_INSTALL_KEY = 'swe@EarthmanWeb'


def resolve_installed_plugin(plugin_key: str = _PLUGIN_INSTALL_KEY) -> Tuple[Optional[str], Optional[str]]:
    """Resolve the AUTHORITATIVE installed plugin root + version.

    The version/memories a hook or MCP server should serve is the one the
    plugin is currently INSTALLED at (`~/.claude/plugins/installed_plugins.json`),
    NOT the ${CLAUDE_PLUGIN_ROOT} a long-lived process was launched under. After
    an in-place update, a still-running MCP server keeps its old launch-time
    root; reading version/memories from that root reports the stale version and
    serves stale `memories:ro`. Resolving from installed_plugins.json makes any
    such process self-correct to the installed version without a restart.

    Returns:
        (install_path, version) for the plugin, or (None, None) if the manifest
        is absent (e.g. a dev checkout — callers fall back to CLAUDE_PLUGIN_ROOT).
    """
    home = os.path.expanduser('~')
    manifest = os.path.join(home, '.claude', 'plugins', 'installed_plugins.json')
    try:
        with open(manifest) as f:
            data = json.load(f)
    except (IOError, json.JSONDecodeError, ValueError):
        return None, None

    entries = (data.get('plugins') or {}).get(plugin_key) or []
    # Prefer a 'user' scope entry; otherwise take the first valid one.
    chosen = None
    for e in entries:
        if e.get('scope') == 'user' and e.get('installPath'):
            chosen = e
            break
    if chosen is None:
        for e in entries:
            if e.get('installPath'):
                chosen = e
                break
    if chosen is None:
        return None, None
    return chosen.get('installPath'), chosen.get('version')


def resolve_plugin_root() -> str:
    """Best plugin root: installed path (authoritative) else CLAUDE_PLUGIN_ROOT.

    Used by version reporting and bundled-memory resolution so updates are
    followed without a process restart. Falls back to the launch-time
    CLAUDE_PLUGIN_ROOT for dev checkouts with no install manifest.
    """
    install_path, _ = resolve_installed_plugin()
    if install_path and os.path.isdir(install_path):
        return install_path
    return os.environ.get('CLAUDE_PLUGIN_ROOT', '')


def get_paths(cwd: str = None) -> Dict[str, str]:
    """Get all relevant paths based on project root.

    Args:
        cwd: Ignored - kept for backward compatibility.
    """
    project_root = get_project_root()
    return {
        "cwd": cwd,
        "project_root": project_root,
        "claude_dir": os.path.join(project_root, ".claude"),
        "setup_file": os.path.join(project_root, ".serena", "swe-setup-complete.json"),
        "learning_file": os.path.join(project_root, ".claude", "learning.json"),
        "plugin_dir": os.path.join(project_root, ".claude", "plugins", "swe"),
        "instructions_dir": os.path.join(project_root, ".claude", "plugins", "swe", "memories", "instructions"),
        "references_dir": os.path.join(project_root, ".claude", "plugins", "swe", "memories", "references"),
        "serena_memories": os.path.join(project_root, ".serena", "memories"),
    }


# =============================================================================
# Decoupled State File Management
# State files live in .serena/swe-state/ and are the authoritative source
# of workflow state, immune to Serena's MCP file caching.
# =============================================================================

def get_state_dir() -> str:
    return os.path.join(get_project_root(), '.serena', 'swe-state')


def get_state_file_path(session_id: str) -> str:
    return os.path.join(get_state_dir(), f'{session_id}.state')


def read_state_file(session_id: str) -> Optional[Dict[str, Any]]:
    """Read decoupled state file (JSON). Returns None if no file.

    State file format:
    {
        "current_state": "WF_EXECUTE",
        "prev_state": "WF_CLASSIFY",
        "ts": 1780111623,
        "session_id": "abc12345",
        "task": "Fix init gate deadlock",
        "features": ["SWE"],
        "progress": ["Fixed sentinel", "Updated thresholds"],
        "return": null
    }
    """
    path = get_state_file_path(session_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            content = f.read().strip()
        if not content:
            return None
        # Try JSON first (new format)
        if content.startswith('{'):
            data = json.loads(content)
            # Normalize: ensure current_state key exists
            if 'current_state' not in data and len(content) > 2:
                return None
            return data
        # Fallback: legacy line-delimited format
        lines = content.split('\n')
        if not lines or not lines[0].strip():
            return None
        result = {'current_state': lines[0].strip()}
        for line in lines[1:]:
            if '=' in line:
                k, _, v = line.partition('=')
                result[k.strip()] = v.strip()
        return result
    except (IOError, json.JSONDecodeError):
        return None


def write_state_file(session_id: str, new_state: str,
                     prev_state: str = None,
                     return_step: str = None,
                     task: str = None,
                     features: list = None,
                     progress: list = None) -> bool:
    """Atomic write to JSON state file. Merges with existing data."""
    state_dir = get_state_dir()
    os.makedirs(state_dir, exist_ok=True)
    path = get_state_file_path(session_id)
    tmp = path + '.tmp'

    # Read existing state to merge (preserve task/features/progress if not provided)
    existing = read_state_file(session_id) or {}

    data = {
        "current_state": new_state,
        "prev_state": prev_state or existing.get("prev_state"),
        "ts": int(datetime.now().timestamp()),
        "session_id": session_id,
        "task": task if task is not None else existing.get("task", ""),
        "features": features if features is not None else existing.get("features", []),
        "progress": progress if progress is not None else existing.get("progress", []),
    }
    if return_step:
        data["return"] = return_step

    try:
        with open(tmp, 'w') as f:
            json.dump(data, f, separators=(',', ':'))
            f.write('\n')
        os.replace(tmp, path)
        return True
    except (IOError, OSError):
        try: os.unlink(tmp)
        except OSError: pass
        return False


# =============================================================================
# WORKING_MEMORY-based State Management (Session-Isolated)
# =============================================================================

def find_working_memory_files(cwd: str) -> List[str]:
    """Find all WORKING_MEMORY files, sorted by date (newest first)."""
    paths = get_paths(cwd)
    memories_dir = paths["serena_memories"]
    
    if not os.path.exists(memories_dir):
        return []
    
    pattern = os.path.join(memories_dir, "WM_*.md")
    files = glob.glob(pattern)
    
    # Sort by filename (which includes timestamp) in reverse order
    files.sort(reverse=True)
    return files


def get_most_recent_working_memory(cwd: str) -> Optional[str]:
    """Get the most recent WORKING_MEMORY file path."""
    files = find_working_memory_files(cwd)
    return files[0] if files else None


def get_working_memory_filename(cwd: str) -> Optional[str]:
    """Get just the filename (without path) of the most recent WORKING_MEMORY."""
    filepath = get_most_recent_working_memory(cwd)
    if filepath:
        return os.path.basename(filepath).replace('.md', '')
    return None


def parse_working_memory_state(content: str) -> Dict[str, Any]:
    """Parse workflow state from WORKING_MEMORY markdown content.
    
    Extracts state from the '## Workflow Context' section.
    """
    state = {
        "current_state": "WF_INIT",
        "feature_keys": [],
        "session_id": None,
        "return_step": None,
        "invocation_mode": "workflow",
        "status": "Starting",
    }
    
    # Find the Workflow Context section
    wf_match = re.search(r'## Workflow Context\s*\n(.*?)(?=\n## |\Z)', content, re.DOTALL)
    if wf_match:
        wf_section = wf_match.group(1)
        
        # Parse key-value pairs
        # Current State takes priority (explicit state for stop hook)
        current_state = re.search(r'\*\*Current State\*\*:\s*(\S+)', wf_section)
        if current_state:
            state["current_state"] = current_state.group(1)
        else:
            # Fall back to Calling Step for backward compatibility
            calling_step = re.search(r'\*\*Calling Step\*\*:\s*(\S+)', wf_section)
            if calling_step:
                state["current_state"] = calling_step.group(1)
        
        feature_keys = re.search(r'\*\*Feature Key\(s\)\*\*:\s*(.+)', wf_section)
        if feature_keys:
            state["feature_keys"] = [k.strip() for k in feature_keys.group(1).split(',')]
        
        session_id = re.search(r'\*\*Session ID\*\*:\s*(\S+)', wf_section)
        if session_id:
            state["session_id"] = session_id.group(1)
        
        return_step = re.search(r'\*\*Return Step\*\*:\s*(\S+)', wf_section)
        if return_step:
            state["return_step"] = return_step.group(1)
        
        invocation_mode = re.search(r'\*\*Invocation Mode\*\*:\s*(\S+)', wf_section)
        if invocation_mode:
            state["invocation_mode"] = invocation_mode.group(1)
    
    # Also parse Session Context for status
    status_match = re.search(r'\*\*Status\*\*:\s*(.+)', content)
    if status_match:
        state["status"] = status_match.group(1).strip()
    
    return state


def update_working_memory_state(content: str, new_state: str, return_step: str = None) -> str:
    """Update the workflow state in WORKING_MEMORY content.

    Modifies the '## Workflow Context' section with new state.
    Returns the updated content.
    """
    # Update Current State (primary field for stop hook)
    if re.search(r'\*\*Current State\*\*:', content):
        content = re.sub(
            r'(\*\*Current State\*\*:\s*)\S+',
            f'\\g<1>{new_state}',
            content
        )

    # Update Calling Step (for backward compatibility)
    content = re.sub(
        r'(\*\*Calling Step\*\*:\s*)\S+',
        f'\\g<1>{new_state}',
        content
    )
    
    # Update Return Step if provided
    if return_step:
        content = re.sub(
            r'(\*\*Return Step\*\*:\s*)\S+',
            f'\\g<1>{return_step}',
            content
        )
    
    # Update Last Updated timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if re.search(r'## Last Updated', content):
        content = re.sub(
            r'(## Last Updated\s*\n).*',
            f'\\g<1>{timestamp}',
            content
        )
    
    return content


def append_transition_to_wm(wm_filepath: str, from_state: str, to_state: str) -> bool:
    """Append a state transition note to WORKING_MEMORY Progress section.

    Args:
        wm_filepath: Path to the WORKING_MEMORY file
        from_state: Previous workflow state
        to_state: New workflow state

    Returns:
        True if successful, False otherwise
    """
    if not wm_filepath or not os.path.exists(wm_filepath):
        return False

    try:
        with open(wm_filepath, 'r') as f:
            content = f.read()

        timestamp = datetime.now().strftime("%H:%M")
        transition_note = f"- [{timestamp}] Transitioned: {from_state} → {to_state}"

        # Find Progress section and append transition note
        progress_match = re.search(r'(## Progress[^\n]*\n)(.*?)(?=\n## |\Z)', content, re.DOTALL)
        updated_content = content

        if progress_match:
            progress_section = progress_match.group(2)

            # Check if there's already a Transitions subsection
            if '### Transitions' in progress_section:
                # Append to existing Transitions subsection
                updated_content = re.sub(
                    r'(### Transitions\s*\n.*?)(\n###|\n##|\Z)',
                    f'\\g<1>{transition_note}\n\\g<2>',
                    content,
                    flags=re.DOTALL
                )
            else:
                # Add Transitions subsection before the next section or at end of Progress
                insert_pos = progress_match.end()
                updated_content = content[:insert_pos] + f"\n### Transitions\n{transition_note}\n" + content[insert_pos:]

        with open(wm_filepath, 'w') as f:
            f.write(updated_content)
        return True
    except IOError:
        return False


def read_working_memory_state(cwd: str, wm_filename: str = None,
                               session_id: str = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Read state from a WORKING_MEMORY file.

    Args:
        cwd: Working directory
        wm_filename: Optional specific WORKING_MEMORY filename (without .md)
                    If None, uses most recent WORKING_MEMORY file
        session_id: Optional session ID. If provided, overrides state from
                   decoupled state file (authoritative source).

    Returns:
        Tuple of (state_dict, wm_filepath) or (None, None) if not found
    """
    paths = get_paths(cwd)

    if wm_filename:
        filepath = os.path.join(paths["serena_memories"], f"{wm_filename}.md")
    else:
        filepath = get_most_recent_working_memory(cwd)

    if not filepath or not os.path.exists(filepath):
        return None, None

    try:
        with open(filepath, 'r') as f:
            content = f.read()
        state = parse_working_memory_state(content)

        # Override with decoupled state file if available
        sid = session_id or state.get('session_id')
        if sid:
            # Ensure session_id is always populated in state dict.
            # parse_working_memory_state only finds it in ## Workflow Context,
            # but auto-created WMs put it in ## Session instead. The caller-
            # provided session_id (from transcript UUID) is authoritative.
            if not state.get('session_id'):
                state['session_id'] = sid
            sf = read_state_file(sid)
            if sf:
                state['current_state'] = sf['current_state']
                if 'return' in sf:
                    state['return_step'] = sf['return']

        return state, filepath
    except IOError:
        return None, None


def write_working_memory_state(cwd: str, wm_filepath: str, new_state: str,
                                return_step: str = None,
                                session_id: str = None) -> bool:
    """Update state in decoupled state file (authoritative) and WM (best-effort display).

    Args:
        cwd: Working directory
        wm_filepath: Full path to the WORKING_MEMORY file
        new_state: New workflow state (e.g., 'WF_EXECUTE')
        return_step: Optional return step to set
        session_id: Optional session ID for decoupled state file

    Returns:
        True if successful, False otherwise
    """
    # 1. State file first (authoritative) — merges with existing task/features/progress
    if session_id:
        current = read_state_file(session_id)
        prev = current.get('current_state') if current else None
        write_state_file(session_id, new_state, prev_state=prev, return_step=return_step)

    # 2. WM update (best-effort, for display only)
    if not os.path.exists(wm_filepath):
        return session_id is not None

    try:
        with open(wm_filepath, 'r') as f:
            content = f.read()

        updated_content = update_working_memory_state(content, new_state, return_step)

        with open(wm_filepath, 'w') as f:
            f.write(updated_content)
        return True
    except IOError:
        return session_id is not None


# =============================================================================
# Legacy Compatibility Layer
# These functions now use WORKING_MEMORY as the source of truth
# =============================================================================

def load_workflow_state(cwd: str, wm_filename: str = None) -> Optional[Dict[str, Any]]:
    """Load workflow state from WORKING_MEMORY file.
    
    NOTE: State is now stored in WORKING_MEMORY files, not a global JSON file.
    This allows multiple concurrent sessions without state conflicts.
    """
    state, filepath = read_working_memory_state(cwd, wm_filename)
    
    if state is None:
        return None
    
    # Convert to legacy format for backward compatibility
    return {
        "session_id": state.get("session_id"),
        "current_state": state.get("current_state", "WF_INIT"),
        "previous_state": None,
        "working_memory_file": os.path.basename(filepath).replace('.md', '') if filepath else None,
        "edits_since_checkpoint": 0,
        "is_swarm_agent": False,
        "plan_mode": False,
    }


def save_workflow_state(cwd: str, state: Dict[str, Any], wm_filepath: str = None) -> bool:
    """Save workflow state to WORKING_MEMORY file.
    
    NOTE: If no wm_filepath provided, finds the most recent WORKING_MEMORY.
    """
    if wm_filepath is None:
        wm_filepath = get_most_recent_working_memory(cwd)
    
    if wm_filepath is None:
        # No WORKING_MEMORY file exists - can't save state
        # This is expected at session start before WM is created
        return False
    
    new_state = state.get("current_state", "WF_INIT")
    return write_working_memory_state(cwd, wm_filepath, new_state)


def load_setup_status(cwd: str) -> Optional[Dict[str, Any]]:
    """Load setup completion status."""
    paths = get_paths(cwd)
    setup_file = paths["setup_file"]

    if not os.path.exists(setup_file):
        return None

    try:
        with open(setup_file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


# Alias for backward compatibility
load_setup_complete = load_setup_status


def save_setup_complete(cwd: str, status: Dict[str, Any]) -> bool:
    """Save setup completion status."""
    paths = get_paths(cwd)
    setup_file = paths["setup_file"]
    os.makedirs(os.path.dirname(setup_file), exist_ok=True)
    try:
        with open(setup_file, 'w') as f:
            json.dump(status, f, indent=2)
        return True
    except IOError:
        return False


def get_reference_content(cwd: str, ref_name: str) -> Optional[str]:
    """Get content of a reference file."""
    paths = get_paths(cwd)
    ref_file = os.path.join(paths["references_dir"], f"{ref_name}.md")
    if os.path.exists(ref_file):
        try:
            with open(ref_file, 'r') as f:
                return f.read()
        except IOError:
            return None
    return None


def is_setup_complete(cwd: str) -> bool:
    """Check if initial setup is complete."""
    status = load_setup_status(cwd)
    return status is not None and status.get("complete", False)


# =============================================================================
# Setup-State Resolution (canonical + legacy + prior-use detection)
#
# Historical bug: plugin <= v1.0.x wrote swe-setup-complete.json into .claude/.
# The current init gate reads it from .serena/ only. A project initialized under
# the old layout therefore looked "unset up" to the gate, which then NO-OPPED
# (treating it as a pristine project) and allowed ALL tools — including Bash —
# before WF_INIT ran. That silently disabled workflow enforcement.
#
# resolve_setup_state() treats a project as initialized if EITHER setup file
# exists (canonical .serena/ OR legacy .claude/) OR if there is prior-use
# evidence under .serena/ (swe-state sessions, WM files). Only a project with
# none of these is "pristine" (safe to leave permissive for onboarding).
# =============================================================================

def _legacy_setup_file(project_root: str) -> str:
    return os.path.join(project_root, ".claude", "swe-setup-complete.json")


def _canonical_setup_file(project_root: str) -> str:
    return os.path.join(project_root, ".serena", "swe-setup-complete.json")


def _read_setup_json(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _has_prior_use(project_root: str) -> bool:
    """True if .serena/ shows evidence this project was used with SWE before."""
    serena = os.path.join(project_root, '.serena')
    if not os.path.isdir(serena):
        return False
    if glob.glob(os.path.join(serena, 'swe-state', '*.state')):
        return True
    if glob.glob(os.path.join(serena, 'memories', 'WM_*.md')):
        return True
    return False


def resolve_setup_state(project_root: str) -> Dict[str, Any]:
    """Resolve setup state from canonical, legacy, and prior-use sources.

    Returns dict:
        initialized: bool   — project has been set up (gate MUST enforce)
        complete:    bool   — setup flag has complete=true
        bootstrapped:bool   — setup flag has bootstrapped=true (init in progress)
        source:      str    — 'canonical' | 'legacy' | 'prior_use' | 'none'
        needs_migration: bool — legacy flag present but canonical missing
        data:        dict|None — the parsed setup flag (canonical preferred)
    """
    canonical = _read_setup_json(_canonical_setup_file(project_root))
    legacy = _read_setup_json(_legacy_setup_file(project_root))
    data = canonical if canonical is not None else legacy

    if canonical is not None:
        source = 'canonical'
    elif legacy is not None:
        source = 'legacy'
    elif _has_prior_use(project_root):
        source = 'prior_use'
    else:
        source = 'none'

    initialized = source != 'none'
    complete = bool(data and data.get('complete'))
    bootstrapped = bool(data and data.get('bootstrapped'))
    needs_migration = canonical is None and legacy is not None
    # Project-level workflow bypass: a "bypass": true field in the SAME
    # swe-setup-complete.json file. When set, all SWE enforcement is skipped
    # and SessionStart announces the bypass + how to remove it.
    bypassed = bool(data and data.get('bypass'))

    return {
        'initialized': initialized,
        'complete': complete,
        'bootstrapped': bootstrapped,
        'bypassed': bypassed,
        'source': source,
        'needs_migration': needs_migration,
        'data': data,
    }


# Brief, reusable notice shown when a project is workflow-bypassed.
BYPASS_NOTICE = (
    "🚫 SWE workflow BYPASSED for this project.\n"
    "To reinstate: set \"bypass\": false (or remove the field) in "
    ".serena/swe-setup-complete.json."
)


def migrate_legacy_setup_file(project_root: str) -> bool:
    """Copy a legacy .claude/swe-setup-complete.json to canonical .serena/.

    Idempotent: no-op if canonical already exists or legacy is absent.
    The legacy file is left in place (harmless once canonical exists); callers
    that want it removed can do so explicitly.
    Returns True if a migration write occurred.
    """
    canonical_path = _canonical_setup_file(project_root)
    if os.path.exists(canonical_path):
        return False
    legacy = _read_setup_json(_legacy_setup_file(project_root))
    if legacy is None:
        return False
    legacy.setdefault('migrated_from', '.claude/swe-setup-complete.json')
    try:
        os.makedirs(os.path.dirname(canonical_path), exist_ok=True)
        with open(canonical_path, 'w') as f:
            json.dump(legacy, f, indent=2)
        return True
    except (IOError, OSError):
        return False


def generate_session_id() -> str:
    """Generate a new session ID based on timestamp."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def create_initial_state(session_id: str = None) -> Dict[str, Any]:
    """Create initial workflow state."""
    if session_id is None:
        session_id = generate_session_id()

    return {
        "session_id": session_id,
        "current_state": "UNINITIALIZED",
        "previous_state": None,
        "edits_since_checkpoint": 0,
        "is_swarm_agent": False,
        "plan_mode": False,
        "working_memory_file": None,
    }
