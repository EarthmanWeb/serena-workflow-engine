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


def get_paths(cwd: str) -> Dict[str, str]:
    """Get all relevant paths based on working directory."""
    return {
        "cwd": cwd,
        "claude_dir": os.path.join(cwd, ".claude"),
        "setup_file": os.path.join(cwd, ".claude", "setup-complete.json"),
        "learning_file": os.path.join(cwd, ".claude", "learning.json"),
        "plugin_dir": os.path.join(cwd, ".claude", "plugins", "serena-workflow-engine"),
        "instructions_dir": os.path.join(cwd, ".claude", "plugins", "serena-workflow-engine", "state-machine", "instructions"),
        "references_dir": os.path.join(cwd, ".claude", "plugins", "serena-workflow-engine", "state-machine", "references"),
        "serena_memories": os.path.join(cwd, ".serena", "memories"),
    }


# =============================================================================
# WORKING_MEMORY-based State Management (Session-Isolated)
# =============================================================================

def find_working_memory_files(cwd: str) -> List[str]:
    """Find all WORKING_MEMORY files, sorted by date (newest first)."""
    paths = get_paths(cwd)
    memories_dir = paths["serena_memories"]
    
    if not os.path.exists(memories_dir):
        return []
    
    pattern = os.path.join(memories_dir, "WORKING_MEMORY_*.md")
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


def read_working_memory_state(cwd: str, wm_filename: str = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Read state from a WORKING_MEMORY file.
    
    Args:
        cwd: Working directory
        wm_filename: Optional specific WORKING_MEMORY filename (without .md)
                    If None, uses most recent WORKING_MEMORY file
    
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
        return state, filepath
    except IOError:
        return None, None


def write_working_memory_state(cwd: str, wm_filepath: str, new_state: str, return_step: str = None) -> bool:
    """Update state in a WORKING_MEMORY file.
    
    Args:
        cwd: Working directory
        wm_filepath: Full path to the WORKING_MEMORY file
        new_state: New workflow state (e.g., 'WF_EXECUTE')
        return_step: Optional return step to set
    
    Returns:
        True if successful, False otherwise
    """
    if not os.path.exists(wm_filepath):
        return False
    
    try:
        with open(wm_filepath, 'r') as f:
            content = f.read()
        
        updated_content = update_working_memory_state(content, new_state, return_step)
        
        with open(wm_filepath, 'w') as f:
            f.write(updated_content)
        
        return True
    except IOError:
        return False


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
        "trajectory_id": None,
        "trajectory_steps": 0,
        "reward_signals": {
            "state_transitions": 0,
            "clarify_count": 0,
            "edit_count": 0,
        }
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
