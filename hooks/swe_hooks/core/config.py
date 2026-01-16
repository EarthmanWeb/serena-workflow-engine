"""Configuration and path helpers for SWE hooks."""

import json
import os
from typing import Dict, Any, Optional
from datetime import datetime


def get_paths(cwd: str) -> Dict[str, str]:
    """Get all relevant paths based on working directory."""
    return {
        "cwd": cwd,
        "claude_dir": os.path.join(cwd, ".claude"),
        "state_file": os.path.join(cwd, ".claude", "workflow-state.json"),
        "setup_file": os.path.join(cwd, ".claude", "setup-complete.json"),
        "learning_file": os.path.join(cwd, ".claude", "learning.json"),
        "plugin_dir": os.path.join(cwd, ".claude", "plugins", "serena-workflow-engine"),
        "instructions_dir": os.path.join(cwd, ".claude", "plugins", "serena-workflow-engine", "state-machine", "instructions"),
        "references_dir": os.path.join(cwd, ".claude", "plugins", "serena-workflow-engine", "state-machine", "references"),
        "serena_memories": os.path.join(cwd, ".serena", "memories"),
    }


def load_workflow_state(cwd: str) -> Optional[Dict[str, Any]]:
    """Load workflow state from JSON file."""
    paths = get_paths(cwd)
    state_file = paths["state_file"]

    if not os.path.exists(state_file):
        return None

    try:
        with open(state_file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_workflow_state(cwd: str, state: Dict[str, Any]) -> bool:
    """Save workflow state to JSON file."""
    paths = get_paths(cwd)
    state_file = paths["state_file"]

    # Ensure .claude directory exists
    os.makedirs(os.path.dirname(state_file), exist_ok=True)

    try:
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
        return True
    except IOError:
        return False


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


def generate_session_id() -> str:
    """Generate a new session ID based on timestamp."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def generate_trajectory_id() -> str:
    """Generate a trajectory ID for RLVR learning."""
    import random
    return f"traj_{int(datetime.now().timestamp())}_{random.randint(10000, 99999)}"


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
        "plan_mode_entries": 0,
        "plan_mode_reason": None,
        "working_memory_file": None,
        "trajectory_id": generate_trajectory_id(),
        "trajectory_steps": 0,
        "learning_complete": False,
        "computed_reward": None,
        "reward_signals": {
            "skill_returns": [],
            "state_transitions": 0,
            "clarify_count": 0,
            "edit_count": 0,
            "checkpoint_compliance": 1.0,
            "test_pass_rate": None,
            "arch_review_pass": None,
            "verify_success": None
        },
        "is_claude_flow_agent": True
    }
