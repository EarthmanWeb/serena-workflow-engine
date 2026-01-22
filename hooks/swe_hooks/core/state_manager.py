"""State machine manager for workflow transitions.

State is stored in WORKING_MEMORY files (session-isolated), NOT in a global state file.
This allows multiple concurrent sessions without state conflicts.
"""

from typing import Dict, Any, Optional, Tuple
from .config import (
    load_workflow_state, save_workflow_state,
    get_most_recent_working_memory, get_working_memory_filename,
    read_working_memory_state, write_working_memory_state,
    persist_edit_to_wm, check_wm_staleness, get_wm_edit_count,
    reset_wm_edit_tracking
)
from .session import (
    extract_session_id, find_working_memory_for_session,
    validate_working_memory_session
)


# State icons for display
STATE_ICONS = {
    "WF_INIT": "🎬",
    "WF_START": "🚀",
    "WF_ONBOARD": "📚",
    "WF_CLASSIFY": "🏷️",
    "WF_LOAD_FEATURE": "📂",
    "WF_RESEARCH": "🔍",
    "WF_DETECT_REQ": "🎯",
    "WF_REQUIREMENT": "📋",
    "WF_CLARIFY": "❓",
    "WF_PLAN_ARCHITECTURE": "🏗️",
    "WF_ARCH_REVIEW": "🔬",
    "WF_EXECUTE": "⚡",
    "WF_CHECKPOINT": "💾",
    "WF_VERIFY": "✅",
    "WF_UPDATE_MEMORY": "📝",
    "WF_DEBUG_TDD": "🐛",
    "WF_CONTINUE": "➡️",
    "WF_SWARM_ORCHESTRATE": "🐝",
    "WF_ASK_PERMISSION": "🔐",
    "WF_CLEANUP": "🧹",
    "WF_DONE": "🎉",
    "WF_INITIAL_SETUP": "⚙️",
}

# States that require plan mode
PLAN_MODE_STATES = {
    "WF_PLAN_ARCHITECTURE",
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

    State is stored in WORKING_MEMORY files, allowing multiple concurrent sessions.
    Each session has its own WORKING_MEMORY file with embedded workflow context.
    """

    def __init__(self, cwd: str, wm_filename: str = None, session_id: str = None):
        """Initialize state manager.

        Args:
            cwd: Working directory
            wm_filename: Optional specific WORKING_MEMORY filename (without .md)
                        If None, finds working memory for session_id
            session_id: Optional session ID for session isolation.
                       If provided, only uses working memory matching this session.
        """
        self.cwd = cwd
        self.wm_filename = wm_filename
        self.wm_filepath = None
        self.session_id = session_id

        # Try to load state from WORKING_MEMORY with session isolation
        state_data = None
        filepath = None

        if wm_filename:
            # Specific filename provided - use it
            state_data, filepath = read_working_memory_state(cwd, wm_filename)
        elif session_id:
            # Session ID provided - find working memory for this session only
            filepath = find_working_memory_for_session(cwd, session_id)
            if filepath:
                state_data, filepath = read_working_memory_state(cwd, filepath.replace('.md', '').split('/')[-1])
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
            # Convert to internal state format
            self.state = {
                "current_state": state_data.get("current_state", "WF_INIT"),
                "previous_state": None,
                "session_id": state_data.get("session_id") or session_id,
                "working_memory_file": self.wm_filename,
                "feature_keys": state_data.get("feature_keys", []),
                "edits_since_checkpoint": 0,
                "plan_mode": state_data.get("current_state") in PLAN_MODE_STATES,
                "reward_signals": {"state_transitions": 0, "edit_count": 0},
            }
        else:
            # No WORKING_MEMORY found for this session - use minimal state
            self.state = {
                "current_state": "WF_INIT",
                "previous_state": None,
                "session_id": session_id,
                "working_memory_file": None,
                "edits_since_checkpoint": 0,
                "plan_mode": False,
                "reward_signals": {"state_transitions": 0, "edit_count": 0},
            }

    def get_current_state(self) -> str:
        """Get current workflow state."""
        return self.state.get("current_state", "UNINITIALIZED")

    def get_icon(self, state: str = None) -> str:
        """Get icon for state."""
        if state is None:
            state = self.get_current_state()
        return STATE_ICONS.get(state, "📍")

    def transition_to(self, new_state: str) -> Tuple[bool, str]:
        """Transition to a new state. Returns (success, message).
        
        State is persisted to the WORKING_MEMORY file if one exists.
        """
        old_state = self.get_current_state()

        # Update in-memory state
        self.state["previous_state"] = old_state
        self.state["current_state"] = new_state
        self.state["reward_signals"]["state_transitions"] = \
            self.state["reward_signals"].get("state_transitions", 0) + 1

        # Handle plan mode
        if new_state in PLAN_MODE_STATES and not self.state.get("plan_mode"):
            self.state["plan_mode"] = True
            self.state["plan_mode_entries"] = self.state.get("plan_mode_entries", 0) + 1
            self.state["plan_mode_reason"] = new_state
        elif new_state in EXIT_PLAN_MODE_STATES and self.state.get("plan_mode"):
            self.state["plan_mode"] = False
            self.state["plan_mode_reason"] = None

        # Save state to WORKING_MEMORY if it exists
        if self.wm_filepath:
            if write_working_memory_state(self.cwd, self.wm_filepath, new_state):
                return True, f"Transition: {old_state} → {new_state}"
            else:
                return False, f"Failed to save state transition to WORKING_MEMORY"
        else:
            # No WORKING_MEMORY yet - state change is in-memory only
            # This is expected at session start before WM is created
            return True, f"Transition: {old_state} → {new_state} (in-memory, no WORKING_MEMORY yet)"

    def increment_edits(self, edited_file: str = None) -> int:
        """Increment edit counter and persist to WM file.
        
        Edit counts are now persisted to WORKING_MEMORY for staleness detection.
        
        Args:
            edited_file: Optional path to the file that was edited
        
        Returns:
            New edit count
        """
        self.state["edits_since_checkpoint"] = \
            self.state.get("edits_since_checkpoint", 0) + 1
        self.state["reward_signals"]["edit_count"] = \
            self.state["reward_signals"].get("edit_count", 0) + 1
        
        # Persist to WORKING_MEMORY file if available
        if self.wm_filepath:
            success, wm_count = persist_edit_to_wm(self.cwd, self.wm_filepath, edited_file)
            if success:
                # Use the persisted count as source of truth
                self.state["edits_since_checkpoint"] = wm_count
        
        return self.state["edits_since_checkpoint"]

    def reset_edit_counter(self):
        """Reset edit counter after checkpoint (user updated WM progress)."""
        self.state["edits_since_checkpoint"] = 0
        
        # Reset in WORKING_MEMORY file if available
        if self.wm_filepath:
            try:
                with open(self.wm_filepath, 'r') as f:
                    content = f.read()
                updated_content = reset_wm_edit_tracking(content)
                with open(self.wm_filepath, 'w') as f:
                    f.write(updated_content)
            except IOError:
                pass  # Silent fail - in-memory reset still works

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
        
        # Reload state from the new WORKING_MEMORY file
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

    def increment_trajectory_step(self):
        """Increment trajectory step counter for RLVR.
        
        Trajectory steps are kept in-memory only - they're session-local.
        """
        self.state["trajectory_steps"] = self.state.get("trajectory_steps", 0) + 1
        # Note: Not persisting - trajectory steps are session-local

    def save(self) -> bool:
        """Save current state to WORKING_MEMORY file."""
        if self.wm_filepath:
            return write_working_memory_state(
                self.cwd, 
                self.wm_filepath, 
                self.state.get("current_state", "WF_INIT")
            )
        return False  # No WORKING_MEMORY to save to
