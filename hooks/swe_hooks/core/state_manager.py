"""State machine manager for workflow transitions.

State is stored in WM files (session-isolated), NOT in a global state file.
This allows multiple concurrent sessions without state conflicts.
"""

import json
import os
from typing import Dict, Any, Optional, Tuple, List
from .config import (
    load_workflow_state, save_workflow_state,
    get_most_recent_working_memory, get_working_memory_filename,
    read_working_memory_state, write_working_memory_state,
    read_state_file, write_state_file,
    get_project_root
)
from .session import (
    extract_session_id, find_working_memory_for_session,
    validate_working_memory_session
)


# Cache for transition matrix
_transition_matrix_cache = None


def load_transition_matrix() -> Dict[str, List[str]]:
    """Load the transition matrix from states.json.

    Returns:
        Dict mapping state names to list of valid next states.
    """
    global _transition_matrix_cache

    if _transition_matrix_cache is not None:
        return _transition_matrix_cache

    # Derive plugin root from __file__: core/ -> swe_hooks/ -> hooks/ -> plugin root
    plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    states_file = os.path.join(plugin_root, 'state-machine', 'states.json')

    try:
        with open(states_file, 'r') as f:
            data = json.load(f)
            _transition_matrix_cache = data.get('transitionMatrix', {})
            return _transition_matrix_cache
    except (IOError, json.JSONDecodeError):
        # Return permissive matrix if file not found
        return {}


def is_valid_transition(from_state: str, to_state: str) -> Tuple[bool, str]:
    """Check if a state transition is valid.

    Args:
        from_state: Current state
        to_state: Target state

    Returns:
        Tuple of (is_valid, error_message)
    """
    matrix = load_transition_matrix()

    # FAIL CLOSED: If matrix can't load, only allow init transitions
    if not matrix:
        if from_state in ("WF_INIT", "UNINITIALIZED", "SessionStart"):
            return True, ""
        return False, "BLOCKED: State machine unavailable. Only WF_INIT transitions allowed."

    # Special case: WF_INIT can go anywhere (session start)
    if from_state in ("WF_INIT", "UNINITIALIZED", "SessionStart"):
        return True, ""

    # Special case: WF_CLARIFY can return to caller (any state)
    if from_state == "WF_CLARIFY":
        return True, ""

    # Check if from_state exists in matrix
    if from_state not in matrix:
        return False, f"BLOCKED: Unknown state {from_state}. Valid states: {', '.join(matrix.keys())}"

    valid_targets = matrix[from_state]

    # Check if to_state is valid
    if to_state in valid_targets:
        return True, ""

    # Invalid transition
    return False, (
        f"BLOCKED: Invalid transition {from_state} → {to_state}. "
        f"Valid next states from {from_state}: {', '.join(valid_targets)}"
    )


# State icons for display (15 states - v3.0)
STATE_ICONS = {
    "WF_INIT": "🎬",
    "WF_START": "🚀",
    "WF_ONBOARD": "📚",
    "WF_CLASSIFY": "🏷️",
    "WF_LOAD_FEATURE": "📂",
    "WF_RESEARCH": "🔍",
    "WF_CLARIFY": "❓",
    "WF_ARCH_REVIEW": "🔬",
    "WF_EXECUTE": "⚡",
    "WF_CHECKPOINT": "💾",
    "WF_VERIFY": "✅",
    "WF_DEBUG_TDD": "🐛",
    "WF_CONTINUE": "➡️",
    "WF_SWARM_ORCHESTRATE": "🐝",
    "WF_DONE": "🎉",
    "WF_INITIAL_SETUP": "⚙️",
}

# States that require plan mode
PLAN_MODE_STATES = {
    "WF_ARCH_REVIEW",
}

# States that exit plan mode
EXIT_PLAN_MODE_STATES = {
    "WF_EXECUTE",
    "WF_CHECKPOINT",
    "WF_VERIFY",
    "WF_DEBUG_TDD",
}


class StateManager:
    """Manages workflow state transitions.

    State is stored in WM files, allowing multiple concurrent sessions.
    Each session has its own WM file with embedded workflow context.
    """

    def __init__(self, cwd: str, wm_filename: str = None, session_id: str = None):
        """Initialize state manager.

        Args:
            cwd: Working directory
            wm_filename: Optional specific WM filename (without .md)
                        If None, finds working memory for session_id
            session_id: Optional session ID for session isolation.
                       If provided, only uses working memory matching this session.
        """
        self.cwd = cwd
        self.wm_filename = wm_filename
        self.wm_filepath = None
        self.session_id = session_id

        # Try to load state from WM with session isolation
        state_data = None
        filepath = None

        if wm_filename:
            # Specific filename provided - use it
            state_data, filepath = read_working_memory_state(cwd, wm_filename, session_id=session_id)
        elif session_id:
            # Session ID provided - find working memory for this session only
            filepath = find_working_memory_for_session(cwd, session_id)
            if filepath:
                state_data, filepath = read_working_memory_state(cwd, filepath.replace('.md', '').split('/')[-1], session_id=session_id)
            else:
                # No WM found — fallback to decoupled state file
                sf = read_state_file(session_id)
                if sf:
                    state_data = {'current_state': sf['current_state'], 'session_id': session_id}
        else:
            # No session context - fall back to most recent (legacy behavior)
            state_data, filepath = read_working_memory_state(cwd)

        # Validate session ownership if session_id provided
        if filepath and session_id and not validate_working_memory_session(filepath, session_id):
            # Working memory doesn't belong to this session - don't use it
            state_data = None
            filepath = None

        if state_data:
            self.wm_filepath = filepath
            self.wm_filename = filepath.replace('.md', '').split('/')[-1] if filepath else None
            self.state = {
                "current_state": state_data.get("current_state", "WF_INIT"),
                "previous_state": None,
                "session_id": state_data.get("session_id") or session_id,
                "working_memory_file": self.wm_filename,
                "feature_keys": state_data.get("feature_keys", []),
                "edits_since_checkpoint": 0,
                "plan_mode": state_data.get("current_state") in PLAN_MODE_STATES,
            }
        else:
            self.state = {
                "current_state": "WF_INIT",
                "previous_state": None,
                "session_id": session_id,
                "working_memory_file": None,
                "edits_since_checkpoint": 0,
                "plan_mode": False,
            }

    def get_current_state(self) -> str:
        """Get current workflow state."""
        return self.state.get("current_state", "UNINITIALIZED")

    def get_icon(self, state: str = None) -> str:
        """Get icon for state."""
        if state is None:
            state = self.get_current_state()
        return STATE_ICONS.get(state, "📍")

    def transition_to(self, new_state: str, force: bool = False) -> Tuple[bool, str]:
        """Transition to a new state. Returns (success, message).

        Validates the transition against the state machine's transition matrix.
        State is persisted to the WM file if one exists.

        Args:
            new_state: The target state to transition to
            force: If True, skip validation (use with caution)

        Returns:
            Tuple of (success, message). If validation fails, success=False
            and message contains the blocking reason.
        """
        old_state = self.get_current_state()

        # Validate the transition unless forced
        if not force:
            is_valid, error_msg = is_valid_transition(old_state, new_state)
            if not is_valid:
                return False, error_msg

        # Update in-memory state
        self.state["previous_state"] = old_state
        self.state["current_state"] = new_state

        # Handle plan mode
        if new_state in PLAN_MODE_STATES and not self.state.get("plan_mode"):
            self.state["plan_mode"] = True
            self.state["plan_mode_entries"] = self.state.get("plan_mode_entries", 0) + 1
            self.state["plan_mode_reason"] = new_state
        elif new_state in EXIT_PLAN_MODE_STATES and self.state.get("plan_mode"):
            self.state["plan_mode"] = False
            self.state["plan_mode_reason"] = None

        # Save state — decoupled state file is authoritative
        sid = self.session_id or self.state.get("session_id")

        if self.wm_filepath:
            if write_working_memory_state(self.cwd, self.wm_filepath, new_state, session_id=sid):
                return True, f"Transition: {old_state} → {new_state}"
            else:
                return False, f"Failed to save state transition to WM"
        elif sid:
            # No WM yet — write state file only
            if write_state_file(sid, new_state, prev_state=old_state):
                return True, f"Transition: {old_state} → {new_state} (state file only)"
            return False, "Failed to write state file"
        else:
            # No WM and no session — in-memory only
            return True, f"Transition: {old_state} → {new_state} (in-memory, no WM yet)"

    def increment_edits(self, edited_file: str = None) -> int:
        """Increment in-memory edit counter.

        Persistent edit tracking is handled by the stream layer.

        Args:
            edited_file: Optional path to the file that was edited (unused,
                        kept for call-site compatibility)

        Returns:
            New edit count
        """
        self.state["edits_since_checkpoint"] = \
            self.state.get("edits_since_checkpoint", 0) + 1
        return self.state["edits_since_checkpoint"]

    def reset_edit_counter(self):
        """Reset in-memory edit counter after checkpoint."""
        self.state["edits_since_checkpoint"] = 0

    def should_checkpoint(self, threshold: int = 3) -> bool:
        """Check if checkpoint is needed based on edit count."""
        return self.state.get("edits_since_checkpoint", 0) >= threshold

    def set_working_memory(self, filename: str):
        """Set the active working memory file and reload state from it."""
        self.wm_filename = filename
        paths_module = __import__('swe_hooks.core.config', fromlist=['get_paths'])
        paths = paths_module.get_paths(self.cwd)
        self.wm_filepath = f"{paths['serena_memories']}/{filename}.md"
        self.state["working_memory_file"] = filename
        
        # Reload state from the new WM file
        state_data, _ = read_working_memory_state(self.cwd, filename)
        if state_data:
            self.state["current_state"] = state_data.get("current_state", self.state["current_state"])
            self.state["session_id"] = state_data.get("session_id")
            self.state["feature_keys"] = state_data.get("feature_keys", [])

    def get_working_memory(self) -> Optional[str]:
        """Get the active working memory filename."""
        return self.wm_filename or self.state.get("working_memory_file")

    def is_plan_mode(self) -> bool:
        """Check if currently in plan mode."""
        return self.state.get("plan_mode", False)

    def save(self) -> bool:
        """Save current state to WM file and/or state file."""
        sid = self.session_id or self.state.get("session_id")
        if self.wm_filepath:
            return write_working_memory_state(
                self.cwd,
                self.wm_filepath,
                self.state.get("current_state", "WF_INIT"),
                session_id=sid
            )
        elif sid:
            return write_state_file(
                sid,
                self.state.get("current_state", "WF_INIT")
            )
        return False  # No WM or session to save to
