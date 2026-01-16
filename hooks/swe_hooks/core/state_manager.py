"""State machine manager for workflow transitions."""

from typing import Dict, Any, Optional, Tuple
from .config import load_workflow_state, save_workflow_state, create_initial_state


# State icons for display
STATE_ICONS = {
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
    """Manages workflow state transitions."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.state = load_workflow_state(cwd)
        if self.state is None:
            self.state = create_initial_state()

    def get_current_state(self) -> str:
        """Get current workflow state."""
        return self.state.get("current_state", "UNINITIALIZED")

    def get_icon(self, state: str = None) -> str:
        """Get icon for state."""
        if state is None:
            state = self.get_current_state()
        return STATE_ICONS.get(state, "📍")

    def transition_to(self, new_state: str) -> Tuple[bool, str]:
        """Transition to a new state. Returns (success, message)."""
        old_state = self.get_current_state()

        # Update state
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

        # Save state
        if save_workflow_state(self.cwd, self.state):
            return True, f"Transition: {old_state} → {new_state}"
        else:
            return False, f"Failed to save state transition"

    def increment_edits(self) -> int:
        """Increment edit counter, return new count."""
        self.state["edits_since_checkpoint"] = \
            self.state.get("edits_since_checkpoint", 0) + 1
        self.state["reward_signals"]["edit_count"] = \
            self.state["reward_signals"].get("edit_count", 0) + 1
        save_workflow_state(self.cwd, self.state)
        return self.state["edits_since_checkpoint"]

    def reset_edit_counter(self):
        """Reset edit counter after checkpoint."""
        self.state["edits_since_checkpoint"] = 0
        save_workflow_state(self.cwd, self.state)

    def should_checkpoint(self, threshold: int = 3) -> bool:
        """Check if checkpoint is needed based on edit count."""
        return self.state.get("edits_since_checkpoint", 0) >= threshold

    def set_working_memory(self, filename: str):
        """Set the active working memory file."""
        self.state["working_memory_file"] = filename
        save_workflow_state(self.cwd, self.state)

    def get_working_memory(self) -> Optional[str]:
        """Get the active working memory file."""
        return self.state.get("working_memory_file")

    def is_plan_mode(self) -> bool:
        """Check if currently in plan mode."""
        return self.state.get("plan_mode", False)

    def increment_trajectory_step(self):
        """Increment trajectory step counter for RLVR."""
        self.state["trajectory_steps"] = self.state.get("trajectory_steps", 0) + 1
        save_workflow_state(self.cwd, self.state)

    def save(self) -> bool:
        """Save current state to disk."""
        return save_workflow_state(self.cwd, self.state)
